"""The baseline: ordinary document RAG, done the ordinary way.

Chunk the published documents, embed the chunks, take the top-k most similar to the
question, hand them to the model, get an answer. No dates, no jurisdictions, no
relationships, no verification. This is what most "AI assistant over our guidance"
systems are, and it is what the brief describes failing.

It is built over the *same* source documents as the graph, so the comparison is
fair, and it uses the *same* composer model, so the difference is the layer, not the
model. The evals run every gold question through both.
"""

from __future__ import annotations

import re

import psycopg
from pydantic import BaseModel, Field

from vgl.config import settings
from vgl.llm import LLM, llm as default_llm

_VISIBLE = "(ch.created_release <= %(r)s AND (ch.retired_release IS NULL OR ch.retired_release > %(r)s))"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string", "description": "A direct, professional answer in 2–5 sentences."},
        "conclusion": {"type": "string", "enum": ["yes", "no", "depends", "not_covered"]},
        "cited": {"type": "array", "items": {"type": "integer"}, "description": "Indexes of the passages relied on."},
    },
    "required": ["answer", "conclusion", "cited"],
}

SYSTEM = """You are an assistant for compliance professionals. Answer the question using the numbered passages from the organisation's published standards and guidance. Be direct and specific, cite the passages you rely on by index, and give a clear conclusion."""


class NaiveAnswer(BaseModel):
    answer: str
    conclusion: str
    passages: list[dict]
    cited_passages: list[dict]
    cited_versions: list[str] = Field(default_factory=list)
    model: str


_REF = re.compile(r"^\*\*((?:\d\.[A-Z]\.\d+)|(?:1\.D\.\d+))")


def _versions_for_chunk(conn: psycopg.Connection, chunk: dict) -> list[str]:
    """Map a cited passage back to the clause version(s) it reproduces, for the evals."""
    m = _REF.match(chunk["text"])
    if m:
        rows = conn.execute(
            "SELECT version_id FROM nodes WHERE source_doc = %s AND display_ref = %s",
            (chunk["document_id"], m.group(1)),
        ).fetchall()
        return [r["version_id"] for r in rows]
    # Non-edition documents (guidance, rulings, notes) have a single version each.
    rows = conn.execute("SELECT version_id FROM nodes WHERE source_doc = %s", (chunk["document_id"],)).fetchall()
    return [r["version_id"] for r in rows]


def ask_naive(conn: psycopg.Connection, question: str, release_id: int, *, k: int = 6,
              llm: LLM = default_llm, model: str | None = None) -> NaiveAnswer:
    [embedding] = llm.embed([question])
    chunks = conn.execute(
        f"""
        SELECT ch.id, ch.document_id, d.title AS document_title, ch.heading, ch.text,
               1 - (ch.embedding <=> %(e)s::vector) AS score
        FROM chunks ch JOIN documents d ON d.id = ch.document_id
        WHERE {_VISIBLE} AND ch.embedding IS NOT NULL
        ORDER BY ch.embedding <=> %(e)s::vector, ch.id
        LIMIT %(k)s
        """,
        {"e": embedding, "r": release_id, "k": k},
    ).fetchall()

    context = "\n\n".join(
        f"[{i}] ({c['document_title']} — {c['heading']})\n{c['text']}" for i, c in enumerate(chunks)
    )
    out = llm.complete_json(
        model=model or settings.composer_model,
        system=SYSTEM,
        user=f"Question: {question.strip()}\n\nPassages:\n\n{context}",
        schema=SCHEMA,
        schema_name="naive_answer",
        max_tokens=800,
    )
    cited_idx = [i for i in out.get("cited", []) if 0 <= i < len(chunks)]
    cited = [dict(chunks[i]) for i in cited_idx]
    cited_versions: list[str] = []
    for c in cited:
        for v in _versions_for_chunk(conn, c):
            if v not in cited_versions:
                cited_versions.append(v)

    def public(c: dict) -> dict:
        return {"document": c["document_title"], "heading": c["heading"], "text": c["text"],
                "score": round(float(c["score"]), 3)}

    return NaiveAnswer(
        answer=out["answer"].strip(), conclusion=out["conclusion"],
        passages=[public(c) for c in chunks], cited_passages=[public(c) for c in cited],
        cited_versions=cited_versions, model=model or settings.composer_model,
    )
