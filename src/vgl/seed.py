"""Load the fictional corpus into Postgres and create Release 1.

Reads data/graph/*.yaml (the structured graph), data/sources/*.md (the prose the
graph was extracted from), data/proposals/*.yaml (changes waiting for an editor), and
writes them with `created_release = 1`. Also chunks the prose for the naive baseline.

The insert functions here are reused by `releases.py` when a proposal is approved,
so a proposal is loaded by exactly the same code path as the seed — there is no
second way for knowledge to enter the graph.

Run:  python -m vgl.seed [--no-embed]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import psycopg
import yaml

from vgl import db
from vgl.config import settings

GRAPH_DIR = settings.data_dir / "graph"
PROPOSALS_DIR = settings.data_dir / "proposals"

_DEFAULT_OBLIGATION = {"definition": "definition", "provision": "must",
                       "guidance": "n/a", "ruling": "n/a", "practice_note": "n/a"}
_DEFAULT_TIER = {"definition": "authoritative", "provision": "authoritative",
                 "guidance": "interpretive", "ruling": "interpretive", "practice_note": "practitioner"}


def _date(v: Any) -> dt.date | None:
    if v is None or isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


# ── insert functions (shared with releases.py) ───────────────────────────────────

def insert_release(conn: psycopg.Connection, release_id: int, label: str,
                   changelog: str = "", created_by: str = "seed") -> None:
    conn.execute(
        "INSERT INTO releases (id, label, changelog, created_by) VALUES (%s, %s, %s, %s)",
        (release_id, label, changelog, created_by),
    )


def insert_documents(conn: psycopg.Connection, docs: list[dict], release_id: int) -> None:
    for d in docs:
        conn.execute(
            """INSERT INTO documents (id, title, tier, published_on, effective_from, body_path, created_release)
               VALUES (%(id)s, %(title)s, %(tier)s, %(published_on)s, %(effective_from)s, %(body_path)s, %(r)s)""",
            {**d, "published_on": _date(d.get("published_on")),
             "effective_from": _date(d.get("effective_from")), "body_path": d.get("body_path"), "r": release_id},
        )
        if d.get("body_path"):
            insert_chunks(conn, d["id"], settings.data_dir / d["body_path"], release_id)


def insert_adoptions(conn: psycopg.Connection, adoptions: list[dict], release_id: int) -> None:
    for a in adoptions:
        conn.execute(
            """INSERT INTO adoptions (document_id, jurisdiction, effective_from, source_doc, created_release)
               VALUES (%s, %s, %s, %s, %s)""",
            (a["document_id"], a["jurisdiction"], _date(a["effective_from"]), a.get("source_doc"), release_id),
        )


def insert_concept(conn: psycopg.Connection, concept_id: str, kind: str, title: str, release_id: int) -> None:
    conn.execute(
        """INSERT INTO concepts (concept_id, kind, title, created_release) VALUES (%s, %s, %s, %s)
           ON CONFLICT (concept_id) DO NOTHING""",
        (concept_id, kind, title, release_id),
    )


def insert_node(conn: psycopg.Connection, concept_id: str, kind: str, v: dict, release_id: int) -> None:
    conn.execute(
        """INSERT INTO nodes (version_id, concept_id, display_ref, tier, obligation, text, parameters,
                              source_doc, effective_from, effective_to, jurisdiction_scope, created_release)
           VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)""",
        (
            v["version_id"], concept_id, v.get("display_ref"),
            v.get("tier", _DEFAULT_TIER[kind]), v.get("obligation", _DEFAULT_OBLIGATION[kind]),
            " ".join(str(v["text"]).split()), json.dumps(v.get("parameters") or {}),
            v["source_doc"], _date(v["effective_from"]), _date(v.get("effective_to")),
            v.get("jurisdiction_scope"), release_id,
        ),
    )


def insert_edges(conn: psycopg.Connection, edges: list[dict], release_id: int) -> None:
    for e in edges:
        conn.execute(
            """INSERT INTO edges (kind, from_concept, to_concept, asserted_by, basis, source_passage, reviewed_by, created_release)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (e["kind"], e["from"], e["to"], e["asserted_by"], e["basis"],
             e.get("source_passage"), e.get("reviewed_by"), release_id),
        )


def insert_bundle(conn: psycopg.Connection, bundle: dict, release_id: int) -> dict[str, int]:
    """Load a proposal bundle (documents, concepts, nodes, edges, adoptions) into a release."""
    counts = {"documents": 0, "nodes": 0, "edges": 0, "adoptions": 0}
    docs = bundle.get("documents") or []
    insert_documents(conn, docs, release_id)
    counts["documents"] = len(docs)
    for n in bundle.get("nodes") or []:
        kind = n.get("kind") or conn.execute(
            "SELECT kind FROM concepts WHERE concept_id = %s", (n["concept_id"],)
        ).fetchone()["kind"]
        insert_concept(conn, n["concept_id"], kind, n.get("title") or n["concept_id"], release_id)
        insert_node(conn, n["concept_id"], kind, n, release_id)
        counts["nodes"] += 1
    insert_edges(conn, bundle.get("edges") or [], release_id)
    counts["edges"] = len(bundle.get("edges") or [])
    insert_adoptions(conn, bundle.get("adoptions") or [], release_id)
    counts["adoptions"] = len(bundle.get("adoptions") or [])
    return counts


# ── chunking for the naive baseline ──────────────────────────────────────────────

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")


def chunk_markdown(text: str) -> list[dict]:
    """Split a Markdown document into paragraph chunks, each tagged with its nearest heading.

    This is the plain, common approach a document-RAG pipeline would take. It is
    deliberately not clever: the point of the baseline is to be representative.
    """
    chunks: list[dict] = []
    heading = ""
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        m = _HEADING.match(block.splitlines()[0])
        if m and len(block.splitlines()) == 1:
            heading = m.group(2).strip()
            continue
        chunks.append({"heading": heading, "text": " ".join(block.split())})
    return chunks


def insert_chunks(conn: psycopg.Connection, document_id: str, path: Path, release_id: int) -> None:
    for i, c in enumerate(chunk_markdown(path.read_text())):
        conn.execute(
            "INSERT INTO chunks (document_id, ordinal, heading, text, created_release) VALUES (%s, %s, %s, %s, %s)",
            (document_id, i, c["heading"], c["text"], release_id),
        )


# ── embeddings ───────────────────────────────────────────────────────────────────

def embed_missing(conn: psycopg.Connection) -> int:
    """Embed every node and chunk that has no embedding yet. Returns the count."""
    from vgl.llm import llm  # imported here so the seed can run without models

    total = 0
    for table, key, text_sql in (
        ("nodes", "version_id", "coalesce(display_ref,'') || ' ' || text"),
        ("chunks", "id", "coalesce(heading,'') || ' ' || text"),
    ):
        rows = conn.execute(
            f"SELECT {key} AS k, {text_sql} AS t FROM {table} WHERE embedding IS NULL ORDER BY {key}"
        ).fetchall()
        if not rows:
            continue
        vectors = llm.embed([r["t"] for r in rows])
        for r, v in zip(rows, vectors):
            conn.execute(f"UPDATE {table} SET embedding = %s WHERE {key} = %s", (v, r["k"]))
        total += len(rows)
    return total


# ── the seed ─────────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def seed(conn: psycopg.Connection, *, embed: bool = True, quiet: bool = False) -> None:
    def say(msg: str) -> None:
        if not quiet:
            print(msg, file=sys.stderr)

    db.drop_schema(conn)
    db.init_schema(conn)

    insert_release(conn, 1, "R1 — seed", "Initial corpus: Editions 2021 and 2025, GS-2025-02, JS adoption notice, PN-001.")

    for j in load_yaml(GRAPH_DIR / "jurisdictions.yaml"):
        conn.execute("INSERT INTO jurisdictions (code, name) VALUES (%s, %s)", (j["code"], j["name"]))

    docs = load_yaml(GRAPH_DIR / "documents.yaml")
    insert_documents(conn, docs["documents"], 1)
    insert_adoptions(conn, docs.get("adoptions") or [], 1)

    n_nodes = 0
    for c in load_yaml(GRAPH_DIR / "nodes.yaml"):
        insert_concept(conn, c["concept_id"], c["kind"], c["title"], 1)
        for v in c.get("versions") or []:
            insert_node(conn, c["concept_id"], c["kind"], v, 1)
            n_nodes += 1

    edges = load_yaml(GRAPH_DIR / "edges.yaml")
    insert_edges(conn, edges, 1)

    for ia in load_yaml(GRAPH_DIR / "issued_answers.yaml"):
        conn.execute(
            """INSERT INTO issued_answers (id, client_name, client_ref, issued_on, jurisdiction, as_of, release_id,
                                           question, outcome, answer_text, cited_versions)
               VALUES (%(id)s, %(client_name)s, %(client_ref)s, %(issued_on)s, %(jurisdiction)s, %(as_of)s,
                       %(release_id)s, %(question)s, %(outcome)s, %(answer_text)s, %(cited_versions)s)""",
            {**ia, "issued_on": _date(ia["issued_on"]), "as_of": _date(ia["as_of"]),
             "answer_text": " ".join(ia["answer_text"].split())},
        )

    n_props = 0
    for p in sorted(PROPOSALS_DIR.glob("*.yaml")):
        prop = load_yaml(p)
        conn.execute(
            """INSERT INTO proposals (id, title, kind, submitted_by, submitted_role, basis, rationale, bundle)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (prop["id"], prop["title"], prop["kind"], prop["submitted_by"], prop["submitted_role"],
             prop["basis"], " ".join(prop["rationale"].split()), json.dumps(prop["bundle"], default=str)),
        )
        n_props += 1

    conn.commit()
    n_chunks = conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
    say(f"Release 1: {len(docs['documents'])} documents, {n_nodes} node versions, {len(edges)} edges, "
        f"{n_chunks} chunks, {n_props} pending proposals")

    if embed:
        n = embed_missing(conn)
        conn.commit()
        say(f"Embedded {n} nodes/chunks with {settings.embed_model} ({settings.embed_dim}d)")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Seed the database to Release 1.")
    ap.add_argument("--no-embed", action="store_true", help="skip embeddings (keyword search still works)")
    args = ap.parse_args(argv)
    with db.connection() as conn:
        seed(conn, embed=not args.no_embed)


if __name__ == "__main__":
    main()
