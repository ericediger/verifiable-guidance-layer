"""The resolver: deterministic, as-of, per-jurisdiction traversal of the graph.

Given a set of entry concepts, a jurisdiction, an as-of date and a release, produce
the EvidencePacket: the version of each relevant concept that was in force on that
date in that place, everything it depends on, everything that interprets or carves
it out, any practitioner note scoped to the place, and — just as important — every
concept the graph knows is relevant but cannot resolve to text (a gap).

Two SQL statements do the work:

  1. A recursive CTE walks outgoing edges from the entry concepts, bounded in depth,
     restricted to edges visible in the release.
  2. One SELECT picks the in-force version per concept: visible in the release,
     scoped to the jurisdiction (or unscoped), in force on the date after applying
     the jurisdiction's adoption delay, choosing the latest such version.

Same inputs and release ⇒ identical packet. This module imports nothing from
`llm.py`, by rule.
"""

from __future__ import annotations

import datetime as dt

import psycopg

from vgl.config import settings
from vgl.contracts import EdgeUsed, EvidencePacket, Gap, ResolvedNode, Superseded, Upcoming

# Which edge kinds the closure follows, and what role the target plays in the packet.
FOLLOW = {
    "DEPENDS_ON_DEFINITION": "definition",
    "INTERPRETED_BY": "interpretation",
    "CARVED_OUT_BY": "carve_out",
    "REFERENCES": "reference",
    "ANNOTATED_BY": "annotation",
}

_VISIBLE = "({t}.created_release <= %(r)s AND ({t}.retired_release IS NULL OR {t}.retired_release > %(r)s))"

_WALK_SQL = f"""
WITH RECURSIVE walk (concept_id, depth, via, from_concept, path) AS (
    SELECT c, 0, NULL::text, NULL::text, ARRAY[c]
    FROM unnest(%(entry)s::text[]) AS c
  UNION ALL
    SELECT e.to_concept, w.depth + 1, e.kind, e.from_concept, w.path || e.to_concept
    FROM walk w
    JOIN edges e ON e.from_concept = w.concept_id
    WHERE w.depth < %(max_depth)s
      AND NOT (e.to_concept = ANY (w.path))
      AND {_VISIBLE.format(t='e')}
)
SELECT concept_id, depth, via, from_concept
FROM walk
ORDER BY depth, concept_id
"""

# The version of each concept in force for (jurisdiction, as_of) in the release.
# in_force_from = the later of the version's own effective date and the date the
# jurisdiction adopted the version's source document (if it adopted it on a delay).
_IN_FORCE_SQL = f"""
SELECT DISTINCT ON (n.concept_id)
       n.version_id, n.concept_id, c.kind, c.title, n.display_ref, n.tier, n.obligation, n.text,
       n.parameters, n.source_doc, d.title AS source_title, n.effective_from, n.jurisdiction_scope,
       GREATEST(n.effective_from, COALESCE(a.effective_from, n.effective_from)) AS in_force_from
FROM nodes n
JOIN concepts c ON c.concept_id = n.concept_id
JOIN documents d ON d.id = n.source_doc
LEFT JOIN adoptions a
       ON a.document_id = n.source_doc AND a.jurisdiction = %(j)s AND {_VISIBLE.format(t='a')}
WHERE n.concept_id = ANY (%(concepts)s::text[])
  AND {_VISIBLE.format(t='n')}
  AND (n.jurisdiction_scope IS NULL OR n.jurisdiction_scope = %(j)s)
  AND GREATEST(n.effective_from, COALESCE(a.effective_from, n.effective_from)) <= %(d)s
  AND (n.effective_to IS NULL OR n.effective_to > %(d)s)
ORDER BY n.concept_id, in_force_from DESC, n.effective_from DESC
"""

# Every visible version of the packet's concepts, with its jurisdiction-adjusted start,
# used to find what comes next (upcoming) and what came before (superseded).
_ALL_VERSIONS_SQL = f"""
SELECT n.version_id, n.concept_id, n.display_ref, n.source_doc, d.title AS source_title,
       n.jurisdiction_scope, n.text, n.effective_from,
       GREATEST(n.effective_from, COALESCE(a.effective_from, n.effective_from)) AS in_force_from
FROM nodes n
JOIN documents d ON d.id = n.source_doc
LEFT JOIN adoptions a
       ON a.document_id = n.source_doc AND a.jurisdiction = %(j)s AND {_VISIBLE.format(t='a')}
WHERE n.concept_id = ANY (%(concepts)s::text[])
  AND {_VISIBLE.format(t='n')}
  AND (n.jurisdiction_scope IS NULL OR n.jurisdiction_scope = %(j)s)
ORDER BY n.concept_id, in_force_from, n.effective_from
"""

_EDGES_SQL = f"""
SELECT kind, from_concept, to_concept, asserted_by, basis, source_passage, reviewed_by
FROM edges e
WHERE from_concept = ANY (%(concepts)s::text[]) AND to_concept = ANY (%(concepts)s::text[])
  AND {_VISIBLE.format(t='e')}
ORDER BY from_concept, kind, to_concept
"""


def current_release(conn: psycopg.Connection) -> int:
    return conn.execute("SELECT max(id) AS id FROM releases").fetchone()["id"]


def resolve(
    conn: psycopg.Connection,
    entry_concepts: list[str],
    jurisdiction: str,
    as_of: dt.date,
    release_id: int | None = None,
    max_depth: int | None = None,
) -> EvidencePacket:
    """Build the evidence packet for a set of entry concepts."""
    r = release_id if release_id is not None else current_release(conn)
    depth_limit = max_depth if max_depth is not None else settings.max_depth
    entry = sorted(set(entry_concepts) | _subjects_of(conn, entry_concepts, r))

    # 1. Walk the graph. Keep the first (shallowest) way each concept was reached.
    walk = conn.execute(_WALK_SQL, {"entry": entry, "max_depth": depth_limit, "r": r}).fetchall()
    reached: dict[str, dict] = {}
    for row in walk:
        reached.setdefault(row["concept_id"], row)
    concepts = list(reached)

    # 2. Pick the in-force version per concept.
    in_force = {
        row["concept_id"]: row
        for row in conn.execute(_IN_FORCE_SQL, {"concepts": concepts, "j": jurisdiction, "d": as_of, "r": r})
    }

    # 3. All visible versions, for upcoming / superseded / gap reasons.
    versions_by_concept: dict[str, list[dict]] = {}
    for row in conn.execute(_ALL_VERSIONS_SQL, {"concepts": concepts, "j": jurisdiction, "r": r}):
        versions_by_concept.setdefault(row["concept_id"], []).append(row)

    titles = {
        row["concept_id"]: row
        for row in conn.execute(
            "SELECT concept_id, kind, title FROM concepts WHERE concept_id = ANY (%s::text[])", (concepts,)
        )
    }

    nodes: list[ResolvedNode] = []
    gaps: list[Gap] = []
    upcoming: list[Upcoming] = []
    superseded: list[Superseded] = []

    for concept_id in concepts:
        how = reached[concept_id]
        role = "entry" if how["depth"] == 0 else FOLLOW[how["via"]]
        chosen = in_force.get(concept_id)
        all_versions = versions_by_concept.get(concept_id, [])

        if chosen is None:
            # Practitioner notes scoped to another jurisdiction are simply absent, not gaps.
            if titles[concept_id]["kind"] == "practice_note":
                continue
            later = [v for v in all_versions if v["in_force_from"] > as_of]
            gaps.append(
                Gap(
                    concept_id=concept_id,
                    title=titles[concept_id]["title"],
                    kind=titles[concept_id]["kind"],
                    reason="not_yet_in_force" if later else "unresolved_reference",
                    referenced_from=how["from_concept"] or concept_id,
                    via=how["via"] or "entry",
                    next_in_force_from=later[0]["in_force_from"] if later else None,
                )
            )
            continue

        nodes.append(
            ResolvedNode(
                version_id=chosen["version_id"],
                concept_id=concept_id,
                kind=chosen["kind"],
                title=chosen["title"],
                display_ref=chosen["display_ref"],
                tier=chosen["tier"],
                obligation=chosen["obligation"],
                text=chosen["text"],
                parameters=chosen["parameters"] or {},
                source_doc=chosen["source_doc"],
                source_title=chosen["source_title"],
                effective_from=chosen["effective_from"],
                in_force_from=chosen["in_force_from"],
                jurisdiction_scope=chosen["jurisdiction_scope"],
                role=role,
                depth=how["depth"],
                via=how["via"],
                from_concept=how["from_concept"],
            )
        )

        chosen_start = chosen["in_force_from"]
        for v in all_versions:
            if v["version_id"] == chosen["version_id"]:
                continue
            if v["in_force_from"] > as_of:
                upcoming.append(
                    Upcoming(
                        concept_id=concept_id,
                        version_id=v["version_id"],
                        display_ref=v["display_ref"],
                        source_doc=v["source_doc"],
                        source_title=v["source_title"],
                        effective_from=v["effective_from"],
                        in_force_from=v["in_force_from"],
                        replaces_version_id=chosen["version_id"],
                        text_changed=v["text"] != chosen["text"],
                    )
                )
            elif v["in_force_from"] < chosen_start:
                superseded.append(
                    Superseded(
                        concept_id=concept_id,
                        version_id=v["version_id"],
                        display_ref=v["display_ref"],
                        source_doc=v["source_doc"],
                        in_force_from=v["in_force_from"],
                        in_force_until=chosen_start,
                        text_changed=v["text"] != chosen["text"],
                    )
                )

    # Only the earliest upcoming version per concept matters for a flag.
    first_upcoming: dict[str, Upcoming] = {}
    for u in sorted(upcoming, key=lambda u: (u.concept_id, u.in_force_from)):
        first_upcoming.setdefault(u.concept_id, u)

    edges = [
        EdgeUsed(**row)
        for row in conn.execute(_EDGES_SQL, {"concepts": concepts, "r": r})
    ]

    # A ruling or guidance statement is a carve-out or an interpretation because of the
    # edge that points at it, not because of the path by which the search reached it.
    modifier_role = {"CARVED_OUT_BY": "carve_out", "INTERPRETED_BY": "interpretation"}
    for n in nodes:
        if n.role in ("entry", "reference"):
            for e in edges:
                if e.to_concept == n.concept_id and e.kind in modifier_role:
                    n.role = modifier_role[e.kind]
                    n.via = e.kind
                    n.from_concept = e.from_concept
                    break

    role_order = {"entry": 0, "carve_out": 1, "interpretation": 2, "definition": 3, "reference": 4, "annotation": 5}
    nodes.sort(key=lambda n: (n.depth, role_order[n.role], n.version_id))

    return EvidencePacket(
        release_id=r,
        jurisdiction=jurisdiction,
        as_of=as_of,
        entry_concepts=entry,
        nodes=nodes,
        edges=edges,
        gaps=sorted(gaps, key=lambda g: g.concept_id),
        upcoming=list(first_upcoming.values()),
        superseded=sorted(superseded, key=lambda s: (s.concept_id, s.in_force_from)),
    )


def _subjects_of(conn: psycopg.Connection, concept_ids: list[str], release_id: int) -> set[str]:
    """The clauses that given rulings/guidance modify. A ruling asked about directly is
    resolved together with the provision it carves out or interprets."""
    rows = conn.execute(
        f"""SELECT e.from_concept FROM edges e
            WHERE e.to_concept = ANY (%(c)s::text[]) AND e.kind IN ('CARVED_OUT_BY','INTERPRETED_BY')
              AND {_VISIBLE.format(t='e')}""",
        {"c": sorted(set(concept_ids)), "r": release_id},
    ).fetchall()
    return {row["from_concept"] for row in rows}


def dependents_of(conn: psycopg.Connection, concept_ids: list[str], release_id: int,
                  max_depth: int | None = None) -> list[dict]:
    """Walk edges *backwards*: which concepts depend on these? Used for impact preview.

    Returns rows of (concept_id, depth, via, from_concept) where from_concept is the
    concept nearer to the changed one.
    """
    depth_limit = max_depth if max_depth is not None else settings.max_depth
    sql = f"""
    WITH RECURSIVE up (concept_id, depth, via, from_concept, path) AS (
        SELECT c, 0, NULL::text, NULL::text, ARRAY[c]
        FROM unnest(%(entry)s::text[]) AS c
      UNION ALL
        SELECT e.from_concept, u.depth + 1, e.kind, e.to_concept, u.path || e.from_concept
        FROM up u
        JOIN edges e ON e.to_concept = u.concept_id
        WHERE u.depth < %(max_depth)s
          AND NOT (e.from_concept = ANY (u.path))
          AND {_VISIBLE.format(t='e')}
    )
    SELECT DISTINCT ON (concept_id) concept_id, depth, via, from_concept
    FROM up WHERE depth > 0
    ORDER BY concept_id, depth
    """
    return conn.execute(sql, {"entry": sorted(set(concept_ids)), "max_depth": depth_limit, "r": release_id}).fetchall()
