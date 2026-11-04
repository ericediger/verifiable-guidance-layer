"""Baseline evidence: the same gold questions through naive document RAG.

These tests record what the baseline does; they do not assert that it fails. A
baseline that happens to get a question right is a data point, not a broken test.
The report shows the failure rate per case; in live mode with --repeat it becomes a
rate across runs, which is the honest way to describe a probabilistic system.
"""

from __future__ import annotations

import pytest

from tests.eval.expectations import naive_failures
from tests.eval.test_gold import GOLD, apply_prerequisites
from vgl import naive

pytestmark = pytest.mark.baseline


@pytest.mark.parametrize("case", GOLD, ids=[c["id"] for c in GOLD])
def test_baseline_case(case, conn, embedded, repeat, results):
    apply_prerequisites(conn, case)
    for _ in range(repeat):
        n = naive.ask_naive(conn, case["question"], case["release"])
        results.record_baseline(case, n, naive_failures(n, case["naive"]))
