"""Turn a gold case's `expect` block into a list of failures for an Answer.

Kept separate from the tests so the impact preview, the report, and a future CI job
can all use the same definition of "correct".
"""

from __future__ import annotations

ANSWERED = {"ANSWER", "ANSWER_WITH_FLAGS"}


def check(answer, expect: dict) -> list[str]:
    f: list[str] = []
    cited = answer.cited_nodes
    flags = answer.flag_kinds
    text = (answer.summary + " " + " ".join(c.text for c in answer.claims)).lower()

    if expect.get("answered") and answer.outcome not in ANSWERED:
        f.append(f"expected an answer, got {answer.outcome}")
    if "outcome" in expect and answer.outcome != expect["outcome"]:
        f.append(f"expected outcome {expect['outcome']}, got {answer.outcome}")
    if "conclusion_in" in expect and answer.conclusion not in expect["conclusion_in"]:
        f.append(f"conclusion {answer.conclusion!r} not in {expect['conclusion_in']}")
    for v in expect.get("must_cite", []):
        if v not in cited:
            f.append(f"must cite {v}")
    for v in expect.get("must_not_cite", []):
        if v in cited:
            f.append(f"must not cite {v}")
    for k in expect.get("required_flags", []):
        if k not in flags:
            f.append(f"missing flag {k}")
    for k in expect.get("forbidden_flags", []):
        if k in flags:
            f.append(f"forbidden flag {k}")
    if "summary_contains_any" in expect:
        if not any(s.lower() in text for s in expect["summary_contains_any"]):
            f.append(f"text contains none of {expect['summary_contains_any']}")
    if "gap_concepts" in expect:
        gaps = {g.concept_id for g in answer.packet.gaps} if answer.packet else set()
        for c in expect["gap_concepts"]:
            if c not in gaps:
                f.append(f"expected gap {c}")
    if "max_claims" in expect and len(answer.claims) > expect["max_claims"]:
        f.append(f"{len(answer.claims)} claims > max {expect['max_claims']}")
    if "clarifications_mention_any" in expect:
        joined = " ".join(answer.clarifications).lower()
        if not any(s.lower() in joined for s in expect["clarifications_mention_any"]):
            f.append(f"clarifications mention none of {expect['clarifications_mention_any']}")
    return f


def naive_failures(naive, spec: dict) -> list[str]:
    f: list[str] = []
    for v in spec.get("failure_if_cites_any", []):
        if v in naive.cited_versions:
            f.append(f"cited {v}")
    for s in spec.get("failure_if_answer_contains_any", []):
        if s.lower() in naive.answer.lower():
            f.append(f"answer says '{s}'")
    if naive.conclusion in spec.get("failure_if_conclusion_in", []):
        f.append(f"conclusion '{naive.conclusion}'")
    lacks = spec.get("failure_if_answer_lacks_all", [])
    if lacks and not any(s.lower() in naive.answer.lower() for s in lacks):
        f.append(f"answer states none of {lacks}")
    return f
