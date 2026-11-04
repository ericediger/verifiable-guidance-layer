"""Entry-point retrieval: find where in the graph a question lands.

Hybrid search over node versions — Postgres full-text search plus pgvector cosine
similarity — fused with reciprocal rank fusion and de-duplicated to concepts. The
output is a short list of entry concepts; the resolver does the rest.

Why it is allowed to be fuzzy: this stage only has to find a reasonable place to
start. Precision comes from the deterministic closure and the verifier downstream.
What it must not do is pretend to find something when nothing is there, so a
coverage gate returns an empty list when the best match is weak.
"""

from __future__ import annotations

import os
import re

import psycopg

from vgl.contracts import QueryFrame
from vgl.llm import LLM, llm as default_llm

_VISIBLE = "(n.created_release <= %(r)s AND (n.retired_release IS NULL OR n.retired_release > %(r)s))"

# Below this cosine similarity, a vector hit does not count as coverage on its own.
COVERAGE_MIN_COSINE = float(os.environ.get("VGL_COVERAGE_MIN_COSINE", "0.30"))
RRF_K = 60
# The vector leg over the bare question is the most reliable signal; weight it up.
VECTOR_WEIGHT = 1.5
_STOP = {"the", "and", "for", "are", "our", "must", "does", "this", "that", "with", "from", "into", "have",
         "has", "been", "when", "what", "which", "will", "should", "can", "could", "would", "its", "their",
         "they", "them", "there", "about", "after", "before", "under", "over", "than", "then", "also", "any",
         "all", "not", "but", "you", "your", "was", "were", "how", "who", "why", "did", "now", "one", "may"}


def _fts(conn: psycopg.Connection, query: str, release_id: int, limit: int = 10) -> list[dict]:
    return conn.execute(
        f"""
        SELECT n.concept_id, n.version_id,
               ts_rank_cd(to_tsvector('english', coalesce(n.display_ref,'') || ' ' || n.text),
                          websearch_to_tsquery('english', %(q)s)) AS score
        FROM nodes n JOIN concepts c ON c.concept_id = n.concept_id
        WHERE {_VISIBLE} AND c.kind <> 'practice_note'
          AND to_tsvector('english', coalesce(n.display_ref,'') || ' ' || n.text)
              @@ websearch_to_tsquery('english', %(q)s)
        ORDER BY score DESC LIMIT %(limit)s
        """,
        {"q": query, "r": release_id, "limit": limit},
    ).fetchall()


def _vector(conn: psycopg.Connection, embedding: list[float], release_id: int, limit: int = 10) -> list[dict]:
    return conn.execute(
        f"""
        SELECT n.concept_id, n.version_id, 1 - (n.embedding <=> %(e)s::vector) AS score
        FROM nodes n JOIN concepts c ON c.concept_id = n.concept_id
        WHERE {_VISIBLE} AND c.kind <> 'practice_note' AND n.embedding IS NOT NULL
        ORDER BY n.embedding <=> %(e)s::vector LIMIT %(limit)s
        """,
        {"e": embedding, "r": release_id, "limit": limit},
    ).fetchall()


def shortlist(conn: psycopg.Connection, frame: QueryFrame, release_id: int,
              k: int = 8, llm: LLM = default_llm) -> list[dict]:
    """Return up to k candidate concepts as dicts {concept_id, kind, title, score, cosine, fts}.

    This is the recall step. It is allowed to over-include; `choose_entries` narrows it.
    An empty list means: nothing in the graph plausibly addresses this question.
    """
    # Keyword leg: the question's words OR-ed together, plus each topic phrase on its own.
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", frame.question) if w.lower() not in _STOP]
    fts_hits = _fts(conn, " OR ".join(dict.fromkeys(words)), release_id) if words else []
    fts_hits += [h for t in frame.topics[:3] for h in _fts(conn, t, release_id, limit=5)]

    # Vector leg: the question alone. Topics would only dilute it.
    vec_hits: list[dict] = []
    try:
        [embedding] = llm.embed([frame.question.strip()])
        vec_hits = _vector(conn, embedding, release_id)
    except Exception:  # no embeddings available (no key, no fixture) → keyword only
        vec_hits = []

    # Reciprocal rank fusion at concept level.
    fused: dict[str, dict] = {}
    for rank, h in enumerate(_dedupe_by_concept(fts_hits)):
        d = fused.setdefault(h["concept_id"], {"concept_id": h["concept_id"], "score": 0.0, "cosine": 0.0, "fts": 0.0})
        d["score"] += 1.0 / (RRF_K + rank)
        d["fts"] = max(d["fts"], float(h["score"]))
    for rank, h in enumerate(_dedupe_by_concept(vec_hits)):
        d = fused.setdefault(h["concept_id"], {"concept_id": h["concept_id"], "score": 0.0, "cosine": 0.0, "fts": 0.0})
        d["score"] += VECTOR_WEIGHT / (RRF_K + rank)
        d["cosine"] = max(d["cosine"], float(h["score"]))

    ranked = sorted(fused.values(), key=lambda d: -d["score"])
    # Coverage gate: a candidate counts only with a keyword hit or a confident vector hit.
    covered = [d for d in ranked if d["fts"] > 0 or d["cosine"] >= COVERAGE_MIN_COSINE][:k]
    if not covered:
        return []
    titles = {
        r["concept_id"]: r for r in conn.execute(
            "SELECT concept_id, kind, title FROM concepts WHERE concept_id = ANY (%s::text[])",
            ([d["concept_id"] for d in covered],))
    }
    for d in covered:
        d["kind"] = titles[d["concept_id"]]["kind"]
        d["title"] = titles[d["concept_id"]]["title"]
    return covered


CHOOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entry_concepts": {
            "type": "array", "items": {"type": "string"},
            "description": "concept_ids from the shortlist that the question primarily turns on; empty if none does",
        },
        "reason": {"type": "string"},
    },
    "required": ["entry_concepts", "reason"],
}

CHOOSE_SYSTEM = """You are given a compliance question and a shortlist of items from a table of contents of investment performance standards (provisions, definitions, interpretive guidance, rulings). Choose the one to three items the question PRIMARILY turns on — the ones a compliance officer would open first.

Rules:
- Pick from the shortlist only, by concept_id. Pick nothing if no item plausibly addresses the question.
- Prefer the provision that states the rule. Add a definition only when the question hinges on what a term means (e.g. whether an account is "discretionary").
- Pick interpretive guidance or a ruling only when the question is specifically about the subject in its title. Do not pick it because it mentions a word in the question.
- Fewer is better. One item is the usual answer; three is the maximum."""


def choose_entries(frame: QueryFrame, candidates: list[dict], llm: LLM = default_llm,
                   model: str | None = None) -> list[str]:
    """The precision step: a small model call picks entry concepts from the shortlist.

    The choice is validated in code — only shortlist IDs are accepted — so the model can
    narrow the search but cannot introduce anything the search did not find.
    """
    if not candidates:
        return []
    from vgl.config import settings

    listing = "\n".join(f"- {c['concept_id']} — {c['title']} ({c['kind']})" for c in candidates)
    out = llm.complete_json(
        model=model or settings.intake_model,
        system=CHOOSE_SYSTEM,
        user=f"Question: {frame.question}\nTopics: {', '.join(frame.topics)}\n\nShortlist:\n{listing}",
        schema=CHOOSE_SCHEMA,
        schema_name="entry_choice",
        max_tokens=300,
    )
    allowed = {c["concept_id"] for c in candidates}
    chosen = [c for c in dict.fromkeys(out.get("entry_concepts", [])) if c in allowed]
    return chosen[:3]


def _dedupe_by_concept(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in sorted(rows, key=lambda r: -float(r["score"])):
        if r["concept_id"] in seen:
            continue
        seen.add(r["concept_id"])
        out.append(r)
    return out
