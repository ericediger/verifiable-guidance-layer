"""The verifier: deterministic checks between the composer and the user.

The composer is a language model. It is good at writing and not to be trusted with
truth. So before anything reaches a person, every claim it wrote is checked against
the evidence packet by plain code:

    V1  every claim cites at least one version
    V2  every cited version is in the packet (no outside knowledge, no invented IDs)
    V3  no cited version is superseded as of the date (no stale citations)
    V4  every carve-out in the packet is reflected: cited by a claim, or raised as a flag
    V5  an unresolved reference in the packet means the answer cannot be final → REVIEW
    V6  practitioner-tier material never grounds a claim

Failures are handled by severity: an ungrounded or stale *supporting* claim is removed
and flagged; an ungrounded *conclusion* fails the answer to REVIEW. Then flags are
derived from the packet itself — carve-outs, pending adoptions, upcoming amendments,
practitioner notes — so the user sees them whether or not the composer mentioned them.

An optional judge (a different model, passed in as a function) may add a soft
faithfulness flag. It can add a flag; it can never pass a claim the rules failed.
This module imports nothing from `llm.py`, by rule.
"""

from __future__ import annotations

from typing import Callable

from vgl.contracts import (
    Answer, Check, Claim, Composition, EvidencePacket, Flag, QueryFrame, Verification,
)

JudgeFn = Callable[[list[Claim], EvidencePacket], list[dict]] | None
"""Given the kept claims and the packet, return one {"faithful": bool, "reason": str} per claim."""


def _conclusion_index(claims: list[Claim]) -> int:
    for i, c in enumerate(claims):
        if c.kind == "conclusion":
            return i
    return 0 if claims else -1


def packet_flags(packet: EvidencePacket) -> list[Flag]:
    """Flags that follow from the evidence alone, independent of what the composer wrote."""
    flags: list[Flag] = []

    for g in packet.gaps:
        if g.reason == "unresolved_reference":
            flags.append(Flag(
                kind="unresolved_reference", concept_id=g.concept_id,
                message=(f"{g.title} is referenced by {g.referenced_from} but is not held in this "
                         f"release. The answer cannot be final until it is reviewed."),
            ))

    for n in packet.nodes:
        if n.role == "carve_out":
            flags.append(Flag(
                kind="carve_out", version_id=n.version_id, concept_id=n.concept_id,
                message=f"{n.display_ref or n.title} creates an exception to {n.from_concept} that may change the conclusion.",
            ))
        elif n.role == "annotation":
            flags.append(Flag(
                kind="practitioner_note", version_id=n.version_id, concept_id=n.concept_id,
                message=f"Practitioner note ({n.jurisdiction_scope or 'all'}): {n.text}",
            ))

    for u in packet.upcoming:
        if not u.text_changed:
            continue
        current = packet.by_version(u.replaces_version_id) if u.replaces_version_id else None
        if current is None:
            continue
        if u.is_adoption_delay(packet.as_of):
            flags.append(Flag(
                kind="pending_adoption", version_id=u.version_id, concept_id=u.concept_id,
                message=(f"{u.source_title} is already in effect elsewhere but applies in {packet.jurisdiction} "
                         f"only from {u.in_force_from.isoformat()}; it changes {current.display_ref or current.title}."),
            ))
        else:
            flags.append(Flag(
                kind="upcoming_amendment", version_id=u.version_id, concept_id=u.concept_id,
                message=(f"{current.display_ref or current.title} changes on {u.in_force_from.isoformat()} "
                         f"({u.source_title}). This answer applies before that date."),
            ))

    entry = [n for n in packet.nodes if n.role == "entry"]
    if entry and all(n.obligation == "should" for n in entry):
        flags.append(Flag(
            kind="recommendation_not_requirement", version_id=entry[0].version_id, concept_id=entry[0].concept_id,
            message=f"{entry[0].display_ref} is a recommendation (\"should\"), not a requirement.",
        ))
    return flags


def verify(frame: QueryFrame, packet: EvidencePacket, composition: Composition,
           judge: JudgeFn = None, composer_model: str | None = None) -> Answer:
    checks: list[Check] = []
    flags = packet_flags(packet)
    kept: list[Claim] = []
    removed: list[Claim] = []
    stale: list[str] = []
    ungrounded_idx: list[int] = []

    groundable = packet.groundable_version_ids()
    superseded_ids = {s.version_id for s in packet.superseded}
    practitioner_ids = {n.version_id for n in packet.nodes if n.tier == "practitioner"}
    conclusion_i = _conclusion_index(composition.claims)
    conclusion_failed = False

    for i, claim in enumerate(composition.claims):
        cites = list(dict.fromkeys(claim.cites))  # de-duplicate, keep order
        problems: list[str] = []

        if not cites:
            problems.append("V1 no citation")
        bad_stale = [v for v in cites if v in superseded_ids]
        bad_outside = [v for v in cites if v not in groundable and v not in superseded_ids and v not in practitioner_ids]
        bad_practitioner = [v for v in cites if v in practitioner_ids]
        if bad_stale:
            stale.extend(bad_stale)
            problems.append(f"V3 stale citation {bad_stale}")
        if bad_outside:
            problems.append(f"V2 citation outside packet {bad_outside}")
        if bad_practitioner:
            problems.append(f"V6 practitioner material cited {bad_practitioner}")

        if problems:
            ungrounded_idx.append(i)
            if i == conclusion_i:
                conclusion_failed = True
            removed.append(claim)
            flags.append(Flag(kind="claim_removed", message=f"Removed: \"{claim.text}\" — {'; '.join(problems)}"))
        else:
            kept.append(claim)

    checks.append(Check(rule="V1", passed=all(c.cites for c in composition.claims),
                        detail="every claim cites at least one version"))
    checks.append(Check(rule="V2", passed=not any("V2" in f.message for f in flags if f.kind == "claim_removed"),
                        detail="every cited version is in the evidence packet"))
    checks.append(Check(rule="V3", passed=not stale, detail=f"stale citations: {stale or 'none'}"))

    carve_outs = [n for n in packet.nodes if n.role == "carve_out"]
    cited_all = {v for c in kept for v in c.cites}
    v4 = all(n.version_id in cited_all or any(f.version_id == n.version_id for f in flags) for n in carve_outs)
    checks.append(Check(rule="V4", passed=v4, detail=f"carve-outs surfaced: {[n.version_id for n in carve_outs] or 'none'}"))

    unresolved = [g for g in packet.gaps if g.reason == "unresolved_reference"]
    checks.append(Check(rule="V5", passed=not unresolved,
                        detail=f"unresolved references: {[g.concept_id for g in unresolved] or 'none'}"))
    checks.append(Check(rule="V6", passed=not any("V6" in f.message for f in flags if f.kind == "claim_removed"),
                        detail="practitioner material never grounds a claim"))

    judge_report = None
    if judge is not None and kept:
        disagreements = []
        for c, verdict in zip(kept, judge(kept, packet)):
            if not verdict.get("faithful", True):
                disagreements.append({"claim": c.text, "reason": verdict.get("reason", "")})
                flags.append(Flag(kind="judge_disagreement",
                                  message=f"A second model questions this claim — \"{c.text}\" — because: {verdict.get('reason', '')}"))
        judge_report = {"checked": len(kept), "disagreements": disagreements}

    verification = Verification(checks=checks, stale_citations=stale, ungrounded_claims=ungrounded_idx,
                                removed_claims=removed, judge=judge_report)

    # ── outcome ──
    if conclusion_failed or not kept:
        outcome = "REVIEW"
        summary = "The composed answer could not be grounded in the evidence in force; routed for review."
    elif composition.conclusion == "not_covered":
        outcome = "REVIEW"
        summary = "The guidance held in this release does not address the question."
    elif unresolved:
        outcome = "REVIEW"
        summary = composition.summary
    elif flags:
        outcome = "ANSWER_WITH_FLAGS"
        summary = composition.summary
    else:
        outcome = "ANSWER"
        summary = composition.summary

    # Flags in a stable, useful order: blockers first, then modifiers, then notes.
    order = {"unresolved_reference": 0, "claim_removed": 1, "carve_out": 2, "pending_adoption": 3,
             "upcoming_amendment": 4, "recommendation_not_requirement": 5, "judge_disagreement": 6,
             "practitioner_note": 7}
    flags.sort(key=lambda f: order[f.kind])

    return Answer(outcome=outcome, summary=summary, conclusion=composition.conclusion, claims=kept, flags=flags,
                  frame=frame, packet=packet, verification=verification, release_id=packet.release_id,
                  composer_model=composer_model)


def clarify(frame: QueryFrame, missing: list[str], release_id: int) -> Answer:
    return Answer(outcome="CLARIFY", summary="More information is needed before this can be answered.",
                  claims=[], flags=[], clarifications=missing, frame=frame, packet=None,
                  verification=None, release_id=release_id)


def no_coverage(frame: QueryFrame, packet: EvidencePacket | None, release_id: int) -> Answer:
    return Answer(outcome="REVIEW", summary="The guidance held in this release does not address the question.",
                  claims=[], flags=[], frame=frame, packet=packet, verification=None, release_id=release_id)
