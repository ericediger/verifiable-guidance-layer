"""Unit tests for releases: proposals, impact preview, approval, pinning, staleness.

These are the two demo scenes as tests. Scene B: a referenced-but-missing ruling is
proposed, previewed, approved; the new release resolves it and the old release still
does not. Scene A: an amendment to a definition is previewed; the provisions that
depend on it and the client answer that relied on it are named before anything is
published.
"""

from __future__ import annotations

import datetime as dt

import pytest

from vgl import closure, releases

pytestmark = pytest.mark.unit

D = dt.date(2025, 6, 1)


def test_seed_parks_two_pending_proposals(conn):
    props = {p["id"]: p for p in releases.list_proposals(conn)}
    assert set(props) == {"prop:QA-2025-031", "prop:A1"}
    assert all(p["status"] == "pending" for p in props.values())
    assert props["prop:QA-2025-031"]["bundle"]["edges"] == [
        "prov:composite-minimum CARVED_OUT_BY ruling:QA-2025-031",
        "ruling:QA-2025-031 DEPENDS_ON_DEFINITION def:significant-cash-flow",
        "ruling:QA-2025-031 DEPENDS_ON_DEFINITION def:measurement-period",
    ]


# ── Scene B ─────────────────────────────────────────────────────────────────────

def test_scene_b_impact_preview_names_the_cases_that_would_change(conn):
    imp = releases.impact_preview(conn, "prop:QA-2025-031")
    assert imp["current_release"] == 1 and imp["would_create_release"] == 2
    assert set(imp["touched_concepts"]) == {"ruling:QA-2025-031", "prov:composite-minimum"}
    assert {d["concept_id"] for d in imp["dependent_concepts"]} >= {"gs:GS-2025-02"}
    changed = {c["id"]: c for c in imp["changed_gold_cases"]}
    assert set(changed) == {"G4a", "G4b"}
    assert changed["G4a"]["before"]["gaps"] == ["ruling:QA-2025-031"]
    assert changed["G4a"]["after"]["gaps"] == []
    assert imp["affected_issued_answers"] == []
    # Preview is read-only.
    assert closure.current_release(conn) == 1
    assert releases.get_proposal(conn, "prop:QA-2025-031")["status"] == "pending"


def test_scene_b_approval_creates_release_2_and_release_1_still_reproduces(conn):
    r2 = releases.approve(conn, "prop:QA-2025-031", "editor:a.okafor", "Verified.", embed=False)
    assert r2 == 2
    after = closure.resolve(conn, ["prov:composite-minimum"], "JN", D, release_id=2)
    assert after.gaps == []
    assert [n.version_id for n in after.nodes if n.role == "carve_out"] == ["ruling:QA-2025-031@v1"]
    assert after.by_version("ruling:QA-2025-031@v1").parameters == {"grace_period_months": 3}
    before = closure.resolve(conn, ["prov:composite-minimum"], "JN", D, release_id=1)
    assert [g.concept_id for g in before.gaps] == ["ruling:QA-2025-031"]
    assert releases.get_proposal(conn, "prop:QA-2025-031")["status"] == "approved"
    # Provenance of the new edge names the proposer and the basis.
    edge = next(e for e in after.edges if e.kind == "CARVED_OUT_BY")
    assert edge.asserted_by == "practitioner:m.delacroix" and edge.basis == "proposal"


def test_a_proposal_cannot_be_decided_twice(conn):
    releases.approve(conn, "prop:QA-2025-031", "editor:a.okafor", embed=False)
    with pytest.raises(ValueError):
        releases.approve(conn, "prop:QA-2025-031", "editor:a.okafor", embed=False)
    with pytest.raises(ValueError):
        releases.reject(conn, "prop:QA-2025-031", "editor:a.okafor", "no")


def test_rejection_is_recorded_with_a_reason(conn):
    releases.reject(conn, "prop:A1", "editor:a.okafor", "Awaiting Board minutes.")
    p = releases.get_proposal(conn, "prop:A1")
    assert p["status"] == "rejected" and p["decision_note"] == "Awaiting Board minutes."
    assert closure.current_release(conn) == 1


# ── Scene A ─────────────────────────────────────────────────────────────────────

def test_scene_a_impact_preview_finds_dependents_and_the_client_answer(conn):
    imp = releases.impact_preview(conn, "prop:A1")
    assert imp["touched_concepts"] == ["def:fee-paying-portfolio"]
    assert {d["concept_id"] for d in imp["dependent_concepts"]} == {
        "prov:composite-inclusion-all-discretionary", "prov:non-fee-paying-inclusion"}
    changed = {c["id"] for c in imp["changed_gold_cases"]}
    assert {"G11a", "G11b"} <= changed
    [ia] = imp["affected_issued_answers"]
    assert ia["id"] == "ia:IA-0001" and ia["client_ref"] == "HPA-77"
    assert ia["staleness"]["status"] == "expires"
    assert ia["staleness"]["from"] == "2026-12-01"
    assert ia["staleness"]["reasons"][0]["learned_after_issue"] is True


def test_scene_a_after_publication_the_definition_flips_on_the_effective_date(conn):
    r = releases.approve(conn, "prop:A1", "editor:a.okafor", embed=False)
    entry = ["prov:composite-inclusion-all-discretionary", "def:fee-paying-portfolio"]
    before = closure.resolve(conn, entry, "JN", dt.date(2026, 11, 15), release_id=r)
    after = closure.resolve(conn, entry, "JN", dt.date(2026, 12, 15), release_id=r)
    assert "def:fee-paying-portfolio@E2025" in before.version_ids()
    assert [u.version_id for u in before.upcoming if u.text_changed] == ["def:fee-paying-portfolio@E2025-A1"]
    assert "def:fee-paying-portfolio@E2025-A1" in after.version_ids()
    # The provision itself never changed.
    assert before.by_version("prov:composite-inclusion-all-discretionary@E2025").text == \
        after.by_version("prov:composite-inclusion-all-discretionary@E2025").text


def test_issued_answer_is_current_until_something_changes(conn):
    [ia] = releases.list_issued_answers(conn, release_id=1)
    assert ia["staleness"]["status"] == "current"
    r = releases.approve(conn, "prop:A1", "editor:a.okafor", embed=False)
    [ia] = releases.list_issued_answers(conn, release_id=r)
    assert ia["staleness"]["status"] == "expires" and ia["staleness"]["from"] == "2026-12-01"
    # And judged from a day after the effective date, it is simply stale.
    raw = conn.execute("SELECT * FROM issued_answers WHERE id = 'ia:IA-0001'").fetchone()
    assert releases.staleness(conn, dict(raw), r, today=dt.date(2026, 12, 2))["status"] == "stale"
