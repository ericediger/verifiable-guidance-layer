"""Unit tests for the resolver: exact expectations, no model involved.

Each test is one of the spec's traps expressed as "given these inputs, the packet
must contain exactly these versions". If one of these fails, the system is wrong in a
way that no amount of prompt engineering can fix — and that is the point.
"""

from __future__ import annotations

import datetime as dt

import pytest

from vgl.closure import dependents_of, resolve

pytestmark = pytest.mark.unit

D_2025_06 = dt.date(2025, 6, 1)


def versions(packet) -> set[str]:
    return packet.version_ids()


# ── G1 · a superseded clause is never selected after its successor takes effect ──

def test_g1_stale_clause_not_selected_after_amendment(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", D_2025_06, release_id=1)
    assert "prov:composite-inclusion-timing@E2025" in versions(p)
    assert "prov:composite-inclusion-timing@E2021" not in versions(p)
    entry = p.by_version("prov:composite-inclusion-timing@E2025")
    assert entry.display_ref == "3.A.6"          # renumbered from 3.A.4
    assert entry.parameters == {"inclusion_deadline_months": 1}
    # The superseded version is still known — as history, not as evidence.
    assert [s.version_id for s in p.superseded if s.concept_id == entry.concept_id] == [
        "prov:composite-inclusion-timing@E2021"
    ]
    assert p.gaps == []


# ── G7 · the same question asked about the past selects the old version ─────────

def test_g7_historical_as_of_selects_prior_edition(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", dt.date(2024, 6, 1), release_id=1)
    assert "prov:composite-inclusion-timing@E2021" in versions(p)
    assert "prov:composite-inclusion-timing@E2025" not in versions(p)
    up = {u.concept_id: u for u in p.upcoming}
    assert up["prov:composite-inclusion-timing"].in_force_from == dt.date(2025, 1, 1)
    assert up["prov:composite-inclusion-timing"].text_changed is True


# ── G2 · jurisdiction with delayed adoption keeps the old edition in force ───────

def test_g2_delayed_adoption_keeps_prior_edition_in_force(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JS", D_2025_06, release_id=1)
    assert "prov:composite-inclusion-timing@E2021" in versions(p)
    assert "prov:composite-inclusion-timing@E2025" not in versions(p)
    # Edition 2025 is coming — the packet says when.
    up = {u.concept_id: u for u in p.upcoming}
    assert up["prov:composite-inclusion-timing"].in_force_from == dt.date(2026, 1, 1)
    assert up["prov:composite-inclusion-timing"].source_doc == "doc:E2025"
    # Identical-text successors are not "changes".
    assert up["def:composite"].text_changed is False


def test_g2_practitioner_note_attached_only_in_its_jurisdiction(conn):
    js = resolve(conn, ["prov:composite-inclusion-timing"], "JS", D_2025_06, release_id=1)
    jn = resolve(conn, ["prov:composite-inclusion-timing"], "JN", D_2025_06, release_id=1)
    assert "note:PN-001@v1" in versions(js)
    assert js.by_version("note:PN-001@v1").tier == "practitioner"
    assert "note:PN-001@v1" not in versions(jn)
    # Practitioner notes never ground a claim.
    assert "note:PN-001@v1" not in js.groundable_version_ids()


# ── G3 · a provision whose text never changed pulls the definition in force ──────

def test_g3_unchanged_provision_resolves_to_current_definition(conn):
    p = resolve(conn, ["prov:composite-inclusion-all-discretionary"], "JN", D_2025_06, release_id=1)
    assert "def:discretionary-portfolio@E2025" in versions(p)
    assert "def:discretionary-portfolio@E2021" not in versions(p)
    assert "def:fee-paying-portfolio@E2025" in versions(p)
    roles = {n.version_id: n.role for n in p.nodes}
    assert roles["def:discretionary-portfolio@E2025"] == "definition"
    # Under the 2021 edition the same provision depended on the old definition.
    old = resolve(conn, ["prov:composite-inclusion-all-discretionary"], "JN", dt.date(2024, 6, 1), release_id=1)
    assert "def:discretionary-portfolio@E2021" in versions(old)
    assert p.by_version("prov:composite-inclusion-all-discretionary@E2025").text == \
        old.by_version("prov:composite-inclusion-all-discretionary@E2021").text


# ── G4a · a referenced-but-missing ruling is a KNOWN gap, not an answer ──────────

def test_g4a_unresolved_reference_is_reported_as_a_gap(conn):
    p = resolve(conn, ["prov:composite-minimum"], "JN", D_2025_06, release_id=1)
    assert "gs:GS-2025-02@v1" in versions(p)
    assert p.by_version("gs:GS-2025-02@v1").role == "interpretation"
    assert [g.concept_id for g in p.gaps] == ["ruling:QA-2025-031"]
    gap = p.gaps[0]
    assert gap.reason == "unresolved_reference"
    assert gap.referenced_from == "gs:GS-2025-02"
    assert gap.via == "REFERENCES"
    # The closure went deep enough to pull the definitions the guidance relies on.
    assert {"def:significant-cash-flow@E2025", "def:measurement-period@E2025"} <= versions(p)


# ── Determinism · same inputs, same packet ──────────────────────────────────────

def test_resolution_is_deterministic(conn):
    a = resolve(conn, ["prov:composite-minimum"], "JN", D_2025_06, release_id=1)
    b = resolve(conn, ["prov:composite-minimum"], "JN", D_2025_06, release_id=1)
    assert a.model_dump_json() == b.model_dump_json()


# ── Reverse walk · impact analysis knows who depends on a definition ────────────

def test_dependents_of_definition_finds_the_provisions_that_use_it(conn):
    rows = dependents_of(conn, ["def:fee-paying-portfolio"], release_id=1)
    dependents = {r["concept_id"] for r in rows}
    assert {"prov:composite-inclusion-all-discretionary", "prov:non-fee-paying-inclusion"} <= dependents
    assert "prov:composite-inclusion-timing" not in dependents
