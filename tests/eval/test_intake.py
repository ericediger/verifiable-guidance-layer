"""Intake evals: the frame must not contain anything the question did not say.

A valid JSON frame that invents a date, a jurisdiction, or a fact is a failure — it
would send the deterministic resolver confidently in the wrong direction.
"""

from __future__ import annotations

import re

import pytest

from vgl import intake

pytestmark = pytest.mark.eval

DATE_LIKE = re.compile(r"\b(20\d\d|19\d\d)\b|\b\d{1,2}/\d{1,2}\b")
JURIS = re.compile(r"\b(JN|JS|GLOBAL|north|south)\b", re.I)


def _frame(q: str):
    return intake.parse(q, jurisdiction=None, as_of=None)


def test_m1_no_date_is_invented(results):
    f = _frame("By when must a new portfolio be added to a composite?")
    blob = " ".join([*f.topics, *f.unresolved, *f.missing_required, *map(str, f.case_facts.values())])
    ok = f.as_of is None and not DATE_LIKE.search(blob)
    results.record_intake("M1", ok, f"as_of={f.as_of} facts={f.case_facts}")
    assert ok


def test_m2_no_jurisdiction_is_invented(results):
    f = _frame("Can we include non-fee-paying portfolios in a composite?")
    blob = " ".join([*f.topics, *map(str, f.case_facts.values()), *map(str, f.case_facts.keys())])
    ok = f.jurisdiction is None and not JURIS.search(blob)
    results.record_intake("M2", ok, f"jurisdiction={f.jurisdiction} facts={f.case_facts}")
    assert ok


def test_m3_relative_date_is_marked_unresolved(results):
    f = _frame("A client withdrew 40% last month and the portfolio is now below our composite minimum. Must we remove it?")
    ok = any("last month" in u.lower() for u in f.unresolved) and not DATE_LIKE.search(" ".join(f.unresolved))
    results.record_intake("M3", ok, f"unresolved={f.unresolved}")
    assert ok


def test_m4_stated_facts_are_captured_and_nothing_required_is_missing(results):
    f = _frame("A client bars us from buying tobacco stocks; the portfolio otherwise follows the strategy. Must it be in a composite?")
    facts = " ".join(f"{k} {v}" for k, v in f.case_facts.items()).lower()
    ok = "tobacco" in facts and f.missing_required == []
    results.record_intake("M4", ok, f"facts={f.case_facts} missing={f.missing_required}")
    assert ok


def test_m5_specific_case_with_no_facts_asks(results):
    f = _frame("Does this portfolio need to be in a composite?")
    joined = " ".join(f.missing_required).lower()
    ok = f.case_facts == {} and "discretionary" in joined and "fee" in joined
    results.record_intake("M5", ok, f"missing={f.missing_required}")
    assert ok
