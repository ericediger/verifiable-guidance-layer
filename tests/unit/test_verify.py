"""Unit tests for the verifier.

Each test hands the verifier a real evidence packet and a composition written by hand
to look like something a model might produce — correct, stale, invented, over-reaching
— and asserts the outcome and the flags. No model is involved: this is the gate, and
the gate must be testable without the thing it gates.
"""

from __future__ import annotations

import datetime as dt

import pytest

from vgl.closure import resolve
from vgl.contracts import Claim, Composition, QueryFrame
from vgl.verify import clarify, packet_flags, verify

pytestmark = pytest.mark.unit

D = dt.date(2025, 6, 1)
FRAME = QueryFrame(question="test", jurisdiction="JN", as_of=D, question_type="timing")


def comp(*claims: Claim, conclusion="yes", summary="Summary.") -> Composition:
    return Composition(summary=summary, conclusion=conclusion, claims=list(claims))


# ── clean answers pass ──────────────────────────────────────────────────────────

def test_grounded_answer_passes(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="By the first full calendar month.", cites=["prov:composite-inclusion-timing@E2025"], kind="conclusion"),
        Claim(text="The inclusion date must be documented.", cites=["prov:composite-inclusion-timing@E2025"]),
    ))
    assert a.outcome == "ANSWER"
    assert a.verification.passed
    assert a.cited_nodes == {"prov:composite-inclusion-timing@E2025"}
    assert a.flags == []


# ── V3 · a stale citation is removed; a stale conclusion fails the answer ───────

def test_stale_supporting_claim_is_removed_and_flagged(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="By the first full calendar month.", cites=["prov:composite-inclusion-timing@E2025"], kind="conclusion"),
        Claim(text="Unless policy specifies an earlier date.", cites=["prov:composite-inclusion-timing@E2021"]),
    ))
    assert a.outcome == "ANSWER_WITH_FLAGS"
    assert a.verification.stale_citations == ["prov:composite-inclusion-timing@E2021"]
    assert "prov:composite-inclusion-timing@E2021" not in a.cited_nodes
    assert "claim_removed" in a.flag_kinds
    assert [c.text for c in a.claims] == ["By the first full calendar month."]


def test_stale_conclusion_fails_to_review(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="By the second full calendar month.", cites=["prov:composite-inclusion-timing@E2021"], kind="conclusion"),
    ))
    assert a.outcome == "REVIEW"
    assert a.claims == []
    assert not a.verification.passed


# ── V1 / V2 · invented or missing citations never reach the user ────────────────

def test_invented_citation_is_removed(conn):
    p = resolve(conn, ["prov:composite-description-on-request"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="Yes, on request.", cites=["prov:composite-description-on-request@E2025"], kind="conclusion"),
        Claim(text="Within ten business days.", cites=["prov:response-deadline@E2025"]),   # does not exist
    ))
    assert a.outcome == "ANSWER_WITH_FLAGS"
    assert [c.text for c in a.claims] == ["Yes, on request."]
    assert any("V2" in f.message for f in a.flags if f.kind == "claim_removed")


def test_uncited_claim_is_removed(conn):
    p = resolve(conn, ["prov:composite-description-on-request"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="Yes, on request.", cites=["prov:composite-description-on-request@E2025"], kind="conclusion"),
        Claim(text="Most firms publish these on their website.", cites=[]),
    ))
    assert [c.text for c in a.claims] == ["Yes, on request."]
    assert any("V1" in f.message for f in a.flags if f.kind == "claim_removed")


# ── V5 · an unresolved reference makes the answer REVIEW even if well grounded ──

def test_g4a_unresolved_reference_forces_review(conn):
    p = resolve(conn, ["prov:composite-minimum"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="Portfolios below the minimum must not be included.", cites=["prov:composite-minimum@E2025"], kind="conclusion"),
    ))
    assert a.outcome == "REVIEW"
    assert a.flags[0].kind == "unresolved_reference"
    assert a.flags[0].concept_id == "ruling:QA-2025-031"
    # The grounded claim is kept for the reviewer; it is the *finality* that is withheld.
    assert len(a.claims) == 1


# ── V6 · practitioner notes are surfaced, never cited ───────────────────────────

def test_g2_practitioner_note_becomes_a_flag_not_a_citation(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JS", D, release_id=1)
    a = verify(FRAME.model_copy(update={"jurisdiction": "JS"}), p, comp(
        Claim(text="By the second full calendar month.", cites=["prov:composite-inclusion-timing@E2021"], kind="conclusion"),
        Claim(text="Examiners expect the month stated explicitly.", cites=["note:PN-001@v1"]),
    ))
    assert a.outcome == "ANSWER_WITH_FLAGS"
    assert "note:PN-001@v1" not in a.cited_nodes
    kinds = a.flag_kinds
    assert {"practitioner_note", "pending_adoption", "claim_removed"} <= kinds
    pending = next(f for f in a.flags if f.kind == "pending_adoption")
    assert "2026-01-01" in pending.message


# ── Flags from the packet alone ─────────────────────────────────────────────────

def test_upcoming_amendment_flag_only_when_text_changes(conn):
    # As of 2024-06, Edition 2025 is upcoming: timing text changes, composite text does not.
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", dt.date(2024, 6, 1), release_id=1)
    kinds = [(f.kind, f.concept_id) for f in packet_flags(p)]
    assert ("upcoming_amendment", "prov:composite-inclusion-timing") in kinds
    assert ("upcoming_amendment", "def:composite") not in kinds


def test_recommendation_is_flagged_as_not_a_requirement(conn):
    p = resolve(conn, ["prov:composite-minimum-no-retroactive-change"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="Not required; recommended.", cites=["prov:composite-minimum-no-retroactive-change@E2025"], kind="conclusion"),
    ))
    assert a.outcome == "ANSWER_WITH_FLAGS"
    assert "recommendation_not_requirement" in a.flag_kinds


def test_not_covered_conclusion_routes_to_review(conn):
    p = resolve(conn, ["prov:composite-description-on-request"], "JN", D, release_id=1)
    a = verify(FRAME, p, comp(
        Claim(text="The material does not address digital assets.", cites=["prov:composite-description-on-request@E2025"], kind="conclusion"),
        conclusion="not_covered",
    ))
    assert a.outcome == "REVIEW"


def test_clarify_lists_what_is_missing():
    a = clarify(QueryFrame(question="Does this portfolio need to be in a composite?"),
                ["discretionary status", "fee-paying status", "jurisdiction", "as_of"], release_id=1)
    assert a.outcome == "CLARIFY"
    assert a.clarifications == ["discretionary status", "fee-paying status", "jurisdiction", "as_of"]
    assert a.claims == []


# ── Judge · can add a flag, cannot pass a failed claim ──────────────────────────

def test_judge_disagreement_is_a_soft_flag(conn):
    p = resolve(conn, ["prov:composite-inclusion-timing"], "JN", D, release_id=1)

    def suspicious_judge(claims, packet):
        return [{"faithful": False, "reason": "the text says first month, not first week"} for _ in claims]

    a = verify(FRAME, p, comp(
        Claim(text="By the first full week.", cites=["prov:composite-inclusion-timing@E2025"], kind="conclusion"),
    ), judge=suspicious_judge)
    assert a.outcome == "ANSWER_WITH_FLAGS"
    assert "judge_disagreement" in a.flag_kinds
    assert a.verification.judge == {"checked": 1, "disagreements": [
        {"claim": "By the first full week.", "reason": "the text says first month, not first week"}]}
