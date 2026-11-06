"""Eval results collector and report writer.

Every gold-case run (layer or baseline) records what happened. At the end of the
session the records are aggregated into the metrics the spec names and written to
docs/eval-report.md (and .json). The report is a deliverable: it is the evidence for
the thesis, produced by the test suite rather than by hand.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import defaultdict
from pathlib import Path

from vgl.config import REPO_ROOT

REPORT_MD = REPO_ROOT / "docs" / "eval-report.md"
REPORT_JSON = REPO_ROOT / "docs" / "eval-report.json"


class Results:
    def __init__(self) -> None:
        self.layer: list[dict] = []
        self.baseline: list[dict] = []
        self.intake: list[dict] = []

    # ── recording ──

    def record_layer(self, case: dict, answer, failures: list[str]) -> None:
        v = answer.verification
        composed = len(answer.claims) + (len(v.removed_claims) if v else 0)
        citations_composed = sum(len(c.cites) for c in answer.claims) + \
            (sum(len(c.cites) for c in v.removed_claims) if v else 0)
        packet_versions = answer.packet.version_ids() if answer.packet else set()
        must_cite = set(case["expect"].get("must_cite", []))
        self.layer.append({
            "id": case["id"], "name": case["name"], "trap": case["trap"],
            "release": case["release"], "jurisdiction": case["jurisdiction"], "as_of": str(case["as_of"]),
            "outcome": answer.outcome, "conclusion": answer.conclusion,
            "summary": answer.summary,
            "cited": sorted(answer.cited_nodes),
            "flags": sorted(answer.flag_kinds),
            "claims_kept": len(answer.claims), "claims_composed": composed,
            "citations_composed": citations_composed,
            "stale_citations": len(v.stale_citations) if v else 0,
            "closure_hit": len(must_cite & packet_versions), "closure_expected": len(must_cite),
            "judge_disagreements": len(v.judge["disagreements"]) if v and v.judge else 0,
            "failures": failures, "passed": not failures,
            "composer_model": answer.composer_model,
        })

    def record_baseline(self, case: dict, naive, failure_reasons: list[str]) -> None:
        self.baseline.append({
            "id": case["id"], "name": case["name"], "trap": case["trap"],
            "conclusion": naive.conclusion, "answer": naive.answer,
            "cited_versions": naive.cited_versions, "failed": bool(failure_reasons),
            "failure_reasons": failure_reasons, "model": naive.model,
        })

    def record_intake(self, case_id: str, passed: bool, detail: str) -> None:
        self.intake.append({"id": case_id, "passed": passed, "detail": detail})

    # ── metrics ──

    def metrics(self) -> dict:
        L = self.layer
        m: dict = {}
        if L:
            m["cases"] = len({r["id"] for r in L})
            m["runs"] = len(L)
            m["pass_rate"] = _rate(sum(r["passed"] for r in L), len(L))
            m["grounded_claim_rate"] = _rate(sum(r["claims_kept"] for r in L), sum(r["claims_composed"] for r in L))
            m["stale_citation_rate_after_verification"] = 0.0   # by construction; see note in report
            m["stale_citations_caught"] = sum(r["stale_citations"] for r in L)
            m["citations_composed"] = sum(r["citations_composed"] for r in L)
            m["closure_recall"] = _rate(sum(r["closure_hit"] for r in L), sum(r["closure_expected"] for r in L))
            abst_expected = [r for r in L if r["trap"] in ("coverage", "clarify") or r["id"] == "G4a"]
            abst_issued = [r for r in L if r["outcome"] in ("REVIEW", "CLARIFY")]
            tp = [r for r in abst_issued if r in abst_expected]
            m["abstention_precision"] = _rate(len(tp), len(abst_issued))
            m["abstention_recall"] = _rate(len(tp), len(abst_expected))
            mods = [r for r in L if any(f in r["flags"] for f in ("carve_out", "pending_adoption", "upcoming_amendment"))]
            mods_expected = [r for r in L if r["id"] in ("G2", "G4b", "G7", "G11a")]
            m["modifier_surfaced_rate"] = _rate(len([r for r in mods_expected if r in mods]), len(mods_expected))
            m["judge_disagreements_total"] = sum(r["judge_disagreements"] for r in L)
        if self.baseline:
            B = self.baseline
            m["baseline_runs"] = len(B)
            m["baseline_failure_rate"] = _rate(sum(r["failed"] for r in B), len(B))
            by_case: dict[str, list] = defaultdict(list)
            for r in B:
                by_case[r["id"]].append(r["failed"])
            m["baseline_failure_rate_by_case"] = {k: _rate(sum(v), len(v)) for k, v in by_case.items()}
        if self.intake:
            m["intake_pass_rate"] = _rate(sum(r["passed"] for r in self.intake), len(self.intake))
        return m

    # ── writing ──

    def write(self) -> None:
        if not (self.layer or self.baseline or self.intake):
            return
        m = self.metrics()
        mode = os.environ.get("VGL_LLM_MODE", "replay")
        lines = [
            "# Eval report",
            "",
            f"Generated {dt.datetime.now().isoformat(timespec='minutes')} · mode **{mode}** · "
            f"{m.get('runs', 0)} layer runs over {m.get('cases', 0)} gold cases · "
            f"{m.get('baseline_runs', 0)} baseline runs",
            "",
            "This file is written by `pytest tests/eval`. It is the evidence for the thesis, produced by the",
            "test suite rather than by hand. See `data/gold.yaml` for what each case requires.",
            "",
            "## Metrics",
            "",
            "| Metric | Value | Meaning |",
            "|---|---|---|",
            f"| Gold pass rate (layer) | {_pct(m.get('pass_rate'))} | Every expectation met: outcome, citations, flags |",
            f"| Composed-claim structural validation rate | {_pct(m.get('grounded_claim_rate'))} | Claims passing V1–V6 ÷ claims composed (structural: cites, in packet, in force, tier — not semantic correctness) |",
            f"| Stale citations composed | {m.get('stale_citations_caught', 0)} of {m.get('citations_composed', 0)} | Citations to a superseded version, before verification; the packet never offers one. After verification the rate is 0 by construction (V3 removes any) |",
            f"| Required gold-evidence coverage | {_pct(m.get('closure_recall'))} | Expected evidence versions present in the packet ÷ expected (the gold set's list, not all relevant evidence) |",
            f"| Modifier surfaced rate | {_pct(m.get('modifier_surfaced_rate'))} | Carve-outs, pending adoptions, upcoming amendments flagged when present |",
            f"| Abstention precision / recall | {_pct(m.get('abstention_precision'))} / {_pct(m.get('abstention_recall'))} | REVIEW/CLARIFY issued when warranted, and only then |",
            f"| Judge disagreements | {m.get('judge_disagreements_total', 0)} | Soft flags from the independent model; never change a verdict |",
            f"| Intake pass rate | {_pct(m.get('intake_pass_rate'))} | No invented dates or jurisdictions; missing facts named |",
            f"| **Baseline failure rate** | **{_pct(m.get('baseline_failure_rate'))}** | Naive RAG, given the question only (no date, no place), classified wrong or unsafe by the rubric in `expectations.py`: cited a superseded version, stated a forbidden phrase, or reached a forbidden conclusion |",
            "",
            "## Per case",
            "",
            "| Case | Trap | Layer outcome | Pass | Cited | Flags | Baseline conclusion | Baseline failed |",
            "|---|---|---|---|---|---|---|---|",
        ]
        base_by_id: dict[str, list] = defaultdict(list)
        for r in self.baseline:
            base_by_id[r["id"]].append(r)
        seen = set()
        for r in self.layer:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            b = base_by_id.get(r["id"], [])
            b_concl = ", ".join(sorted({x["conclusion"] for x in b})) if b else "—"
            b_fail = f"{sum(x['failed'] for x in b)}/{len(b)}" if b else "—"
            cited = "<br>".join(_short(v) for v in r["cited"]) or "—"
            lines.append(f"| {r['id']} | {r['trap']} | {r['outcome']} | {'✅' if r['passed'] else '❌'} | {cited} | "
                         f"{', '.join(r['flags']) or '—'} | {b_concl} | {b_fail} |")
        failures = [r for r in self.layer if not r["passed"]]
        if failures:
            lines += ["", "## Failures", ""]
            for r in failures:
                lines.append(f"- **{r['id']}** ({r['outcome']}): " + "; ".join(r["failures"]))
        if self.baseline:
            lines += ["", "## Baseline answers (what naive RAG said)", ""]
            for r in self.baseline:
                mark = "❌" if r["failed"] else "✅"
                lines.append(f"- **{r['id']}** {mark} *{r['conclusion']}* — {r['answer']}")
                if r["failure_reasons"]:
                    lines.append(f"  - failed because: {'; '.join(r['failure_reasons'])}")
        if self.intake:
            lines += ["", "## Intake evals", ""]
            for r in self.intake:
                lines.append(f"- **{r['id']}** {'✅' if r['passed'] else '❌'} {r['detail']}")
        REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
        REPORT_MD.write_text("\n".join(lines) + "\n")
        REPORT_JSON.write_text(json.dumps(
            {"metrics": m, "layer": self.layer, "baseline": self.baseline, "intake": self.intake}, indent=2, default=str))


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{100 * v:.0f}%"


def _short(version_id: str) -> str:
    return version_id.split(":", 1)[1] if ":" in version_id else version_id
