"""Releases: how knowledge enters the graph, and what happens when it does.

A proposal is a bundle of documents, versions and edges with a named proposer and a
stated basis. An editor previews its impact, then approves (creating a new release
that contains the bundle) or rejects it. Nothing in an earlier release changes.

The impact preview is the governance workflow and the test suite meeting: the bundle
is loaded inside a savepoint, every gold case is re-resolved against the simulated
release, differences are collected, and the savepoint is rolled back. No model is
involved — it is the deterministic resolver run twice.

Staleness of issued answers is computed here too, never stored: for each version an
answer relied on, is there now a later version in force (or due) in that jurisdiction?
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import psycopg
import yaml

from vgl import closure, seed
from vgl.config import settings

GOLD_PATH = settings.data_dir / "gold.yaml"


def load_gold(path: Path = GOLD_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text())


# ── read side ────────────────────────────────────────────────────────────────────

def list_releases(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT r.id, r.label, r.changelog, r.created_by, r.created_at,
                  (SELECT count(*) FROM nodes n WHERE n.created_release <= r.id
                      AND (n.retired_release IS NULL OR n.retired_release > r.id)) AS node_count,
                  (SELECT count(*) FROM edges e WHERE e.created_release <= r.id
                      AND (e.retired_release IS NULL OR e.retired_release > r.id)) AS edge_count,
                  (SELECT count(*) FROM documents d WHERE d.created_release <= r.id
                      AND (d.retired_release IS NULL OR d.retired_release > r.id)) AS document_count
           FROM releases r ORDER BY r.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def list_proposals(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM proposals ORDER BY submitted_at, id"
    ).fetchall()
    return [_proposal_summary(dict(r)) for r in rows]


def get_proposal(conn: psycopg.Connection, proposal_id: str) -> dict:
    row = conn.execute("SELECT * FROM proposals WHERE id = %s", (proposal_id,)).fetchone()
    if row is None:
        raise KeyError(proposal_id)
    p = dict(row)
    p["bundle"] = p["bundle"] if isinstance(p["bundle"], dict) else json.loads(p["bundle"])
    for d in p["bundle"].get("documents") or []:
        if d.get("body_path"):
            d["body"] = (settings.data_dir / d["body_path"]).read_text()
    return p


def _proposal_summary(p: dict) -> dict:
    bundle = p["bundle"] if isinstance(p["bundle"], dict) else json.loads(p["bundle"])
    p["bundle"] = {
        "documents": [d["id"] for d in bundle.get("documents") or []],
        "nodes": [n["version_id"] for n in bundle.get("nodes") or []],
        "edges": [f"{e['from']} {e['kind']} {e['to']}" for e in bundle.get("edges") or []],
    }
    return p


# ── impact preview ───────────────────────────────────────────────────────────────

def _touched_concepts(bundle: dict) -> set[str]:
    """Concepts whose meaning the bundle changes: new versions, and the sources of new edges.

    A definition an edge merely points *to* is not changed by being pointed at.
    """
    touched = {n["concept_id"] for n in bundle.get("nodes") or []}
    touched |= {e["from"] for e in bundle.get("edges") or []}
    return touched


def _packet_signature(packet) -> dict:
    return {
        "versions": sorted(packet.version_ids()),
        "gaps": sorted(g.concept_id for g in packet.gaps),
        "upcoming": sorted(u.version_id for u in packet.upcoming if u.text_changed),
    }


def impact_preview(conn: psycopg.Connection, proposal_id: str) -> dict:
    """What would change if this proposal were published now. Read-only."""
    p = get_proposal(conn, proposal_id)
    bundle = p["bundle"]
    current = closure.current_release(conn)
    simulated = current + 1
    touched = _touched_concepts(bundle)
    gold = load_gold()

    # Baseline: resolve each gold case at the current release (by its entry concepts).
    before = {}
    for g in gold:
        if g["entry_concepts"]:
            before[g["id"]] = _packet_signature(closure.resolve(
                conn, g["entry_concepts"], g["jurisdiction"], _d(g["as_of"]), current))

    conn.execute("SAVEPOINT impact_preview")
    try:
        seed.insert_release(conn, simulated, "simulated", "impact preview", "preview")
        seed.insert_bundle(conn, bundle, simulated)
        dependents = closure.dependents_of(conn, sorted(touched), simulated)
        affected_concepts = sorted(touched | {r["concept_id"] for r in dependents})

        changed_cases = []
        for g in gold:
            if not g["entry_concepts"]:
                continue
            after = _packet_signature(closure.resolve(
                conn, g["entry_concepts"], g["jurisdiction"], _d(g["as_of"]), simulated))
            if after != before[g["id"]]:
                changed_cases.append({
                    "id": g["id"], "name": g["name"], "question": g["question"],
                    "jurisdiction": g["jurisdiction"], "as_of": g["as_of"],
                    "before": before[g["id"]], "after": after,
                })

        affected_answers = []
        for ia in conn.execute("SELECT * FROM issued_answers ORDER BY issued_on").fetchall():
            status = staleness(conn, dict(ia), simulated)
            if status["status"] != "current":
                affected_answers.append({**_issued_public(dict(ia)), "staleness": status})
    finally:
        conn.execute("ROLLBACK TO SAVEPOINT impact_preview")

    return {
        "proposal_id": proposal_id,
        "current_release": current,
        "would_create_release": simulated,
        "touched_concepts": sorted(touched),
        "dependent_concepts": [dict(r) for r in dependents],
        "affected_concepts": affected_concepts,
        "changed_gold_cases": changed_cases,
        "affected_issued_answers": affected_answers,
    }


# ── decisions ────────────────────────────────────────────────────────────────────

def approve(conn: psycopg.Connection, proposal_id: str, decided_by: str, note: str = "",
            embed: bool = True) -> int:
    p = get_proposal(conn, proposal_id)
    if p["status"] != "pending":
        raise ValueError(f"proposal {proposal_id} is already {p['status']}")
    new_release = closure.current_release(conn) + 1
    changelog = f"{p['title']}\n\nProposed by {p['submitted_by']} ({p['submitted_role']}). Basis: {p['basis']}.\n{p['rationale']}"
    seed.insert_release(conn, new_release, f"R{new_release} — {p['title']}", changelog, decided_by)
    seed.insert_bundle(conn, p["bundle"], new_release)
    conn.execute(
        """UPDATE proposals SET status = 'approved', decided_by = %s, decision_note = %s,
                  release_id = %s, decided_at = now() WHERE id = %s""",
        (decided_by, note, new_release, proposal_id),
    )
    if embed:
        seed.embed_missing(conn)
    return new_release


def reject(conn: psycopg.Connection, proposal_id: str, decided_by: str, note: str) -> None:
    p = get_proposal(conn, proposal_id)
    if p["status"] != "pending":
        raise ValueError(f"proposal {proposal_id} is already {p['status']}")
    conn.execute(
        """UPDATE proposals SET status = 'rejected', decided_by = %s, decision_note = %s, decided_at = now()
           WHERE id = %s""",
        (decided_by, note, proposal_id),
    )


# ── issued answers and staleness ─────────────────────────────────────────────────

def staleness(conn: psycopg.Connection, ia: dict, release_id: int, today: dt.date | None = None) -> dict:
    """Is an issued answer still good under `release_id`?

    For each version the answer relied on, look for a later version of the same concept
    that is (or will be) in force in the answer's jurisdiction after the answer's as-of
    date. The earliest such date is when the answer stops being right.
    """
    today = today or dt.date.today()
    reasons = []
    earliest: dt.date | None = None
    for v in ia["cited_versions"]:
        row = conn.execute(
            f"""
            SELECT n.version_id, n.concept_id, n.display_ref, n.source_doc, d.title AS source_title,
                   n.created_release,
                   GREATEST(n.effective_from, COALESCE(a.effective_from, n.effective_from)) AS in_force_from
            FROM nodes n
            JOIN documents d ON d.id = n.source_doc
            LEFT JOIN adoptions a ON a.document_id = n.source_doc AND a.jurisdiction = %(j)s
                 AND a.created_release <= %(r)s AND (a.retired_release IS NULL OR a.retired_release > %(r)s)
            WHERE n.concept_id = (SELECT concept_id FROM nodes WHERE version_id = %(v)s)
              AND n.version_id <> %(v)s
              AND n.created_release <= %(r)s AND (n.retired_release IS NULL OR n.retired_release > %(r)s)
              AND GREATEST(n.effective_from, COALESCE(a.effective_from, n.effective_from)) > %(as_of)s
            ORDER BY in_force_from
            LIMIT 1
            """,
            {"j": ia["jurisdiction"], "r": release_id, "v": v, "as_of": ia["as_of"]},
        ).fetchone()
        if row:
            reasons.append({
                "cited_version": v, "superseding_version": row["version_id"],
                "display_ref": row["display_ref"], "source_title": row["source_title"],
                "from": row["in_force_from"].isoformat(),
                "learned_after_issue": row["created_release"] > ia["release_id"],
            })
            earliest = row["in_force_from"] if earliest is None else min(earliest, row["in_force_from"])

    if earliest is None:
        return {"status": "current", "from": None, "reasons": []}
    status = "stale" if earliest <= today else "expires"
    return {"status": status, "from": earliest.isoformat(), "reasons": reasons}


def _issued_public(ia: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in ia.items()}


def list_issued_answers(conn: psycopg.Connection, release_id: int | None = None) -> list[dict]:
    r = release_id if release_id is not None else closure.current_release(conn)
    out = []
    for ia in conn.execute("SELECT * FROM issued_answers ORDER BY issued_on").fetchall():
        ia = dict(ia)
        out.append({**_issued_public(ia), "staleness": staleness(conn, ia, r)})
    return out


def _d(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))
