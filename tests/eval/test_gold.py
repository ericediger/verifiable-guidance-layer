"""Gold-set evals: every case in data/gold.yaml through the layer.

Default mode replays recorded model responses, so this is deterministic and needs no
network. `--live` runs against the real models; `--repeat N` runs each case N times
and the report shows rates. Expectations are structural (outcome, citations, flags,
gaps), never string-equality on prose.
"""

from __future__ import annotations

import datetime as dt

import pytest

from tests.eval.expectations import check
from vgl import pipeline, releases

GOLD = releases.load_gold()
pytestmark = pytest.mark.eval


def apply_prerequisites(conn, case: dict) -> None:
    """Approve the proposals a case depends on (inside the test's transaction)."""
    needed = case.get("requires_proposal")
    if not needed:
        return
    order = ["prop:QA-2025-031", "prop:A1"]
    for pid in order:
        if releases.get_proposal(conn, pid)["status"] == "pending":
            releases.approve(conn, pid, "editor:a.okafor", "eval prerequisite", embed=True)
        if pid == needed:
            break


@pytest.mark.parametrize("case", GOLD, ids=[c["id"] for c in GOLD])
def test_gold_case(case, conn, embedded, repeat, results):
    apply_prerequisites(conn, case)
    last_failures: list[str] = []
    for _ in range(repeat):
        answer = pipeline.ask(
            conn, case["question"], jurisdiction=case["jurisdiction"],
            as_of=dt.date.fromisoformat(str(case["as_of"])), release_id=case["release"], store=False,
        )
        last_failures = check(answer, case["expect"])
        results.record_layer(case, answer, last_failures)
    assert not last_failures, f"{case['id']} {case['name']}: " + "; ".join(last_failures)
