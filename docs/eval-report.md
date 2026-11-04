# Eval report

Generated 2026-11-04T13:18 · mode **replay** · 13 layer runs over 13 gold cases · 13 baseline runs

This file is written by `pytest tests/eval`. It is the evidence for the thesis, produced by the
test suite rather than by hand. See `data/gold.yaml` for what each case requires.

## Metrics

| Metric | Value | Meaning |
|---|---|---|
| Gold pass rate (layer) | 100% | Every expectation met: outcome, citations, flags |
| Grounded-claim rate | 100% | Composed claims that survived verification |
| Stale citations caught | 0 of 85 composed | Removed before reaching the user; rate after verification is 0 by construction |
| Closure recall | 100% | Expected versions present in the evidence packet |
| Modifier surfaced rate | 100% | Carve-outs, pending adoptions, upcoming amendments flagged when present |
| Abstention precision / recall | 100% / 100% | REVIEW/CLARIFY issued when warranted, and only then |
| Judge disagreements | 5 | Soft flags from the independent model; never change a verdict |
| Intake pass rate | 100% | No invented dates or jurisdictions; missing facts named |
| **Baseline failure rate** | **23%** | Naive RAG wrong or unsafe on the same questions, same model |

## Per case

| Case | Trap | Layer outcome | Pass | Cited | Flags | Baseline conclusion | Baseline failed |
|---|---|---|---|---|---|---|---|
| G1 | stale | ANSWER | ✅ | composite@E2025<br>composite-inclusion-timing@E2025 | — | yes | 0/1 |
| G2 | jurisdiction | ANSWER_WITH_FLAGS | ✅ | composite@E2021<br>composite-inclusion-timing@E2021 | judge_disagreement, pending_adoption, practitioner_note | yes | 1/1 |
| G3 | interaction | ANSWER | ✅ | composite@E2025<br>discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025<br>composite-inclusion-all-discretionary@E2025 | — | depends | 0/1 |
| G4a | carve_out | REVIEW | ✅ | external-cash-flow@E2025<br>measurement-period@E2025<br>significant-cash-flow@E2025<br>GS-2025-02@v1<br>composite-minimum@E2025 | unresolved_reference | depends | 0/1 |
| G4b | carve_out | ANSWER_WITH_FLAGS | ✅ | external-cash-flow@E2025<br>measurement-period@E2025<br>significant-cash-flow@E2025<br>GS-2025-02@v1<br>composite-minimum@E2025<br>QA-2025-031@v1 | carve_out | depends | 0/1 |
| G5 | coverage | REVIEW | ✅ | gross-of-fees-return@E2025 | — | not_covered | 0/1 |
| G6 | clarify | CLARIFY | ✅ | — | — | depends | 0/1 |
| G7 | stale | ANSWER_WITH_FLAGS | ✅ | composite@E2021<br>composite-inclusion-timing@E2021 | judge_disagreement, upcoming_amendment | yes | 1/1 |
| G8 | none | ANSWER | ✅ | composite@E2025<br>composite-description-on-request@E2025 | — | yes | 0/1 |
| G9 | none | ANSWER_WITH_FLAGS | ✅ | composite@E2025<br>discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025<br>non-fee-paying-inclusion@E2025 | judge_disagreement | yes | 0/1 |
| G10 | obligation | ANSWER_WITH_FLAGS | ✅ | composite@E2025<br>composite-minimum-no-retroactive-change@E2025 | judge_disagreement, recommendation_not_requirement | no | 0/1 |
| G11a | amendment | ANSWER_WITH_FLAGS | ✅ | composite@E2025<br>discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025<br>non-fee-paying-inclusion@E2025 | upcoming_amendment | no | 1/1 |
| G11b | amendment | ANSWER_WITH_FLAGS | ✅ | discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025-A1<br>non-fee-paying-inclusion@E2025 | judge_disagreement | no | 0/1 |

## Baseline answers (what naive RAG said)

- **G1** ✅ *yes* — Under the current 2025 Edition, a new portfolio must be included in a composite on a timely and consistent basis, and no later than the beginning of the first full calendar month after it comes under management. The firm must also document the inclusion date it applies for each composite. This tightens the 2021 Edition, which allowed up to the beginning of the second full calendar month unless the firm's composite-specific policy set an earlier date. Separately, a new portfolio below a documented composite minimum should not be included (per GS-2025-02).
- **G2** ❌ *yes* — Under the current 2025 Edition, a new portfolio must be included in a composite on a timely and consistent basis, and no later than the beginning of the first full calendar month after it comes under management. The firm must also document the inclusion date it applies for each composite. This tightens the 2021 Edition, which allowed up to the beginning of the second full calendar month unless the firm's composite-specific policy set an earlier date. Separately, a new portfolio below a documented composite minimum should not be included (per GS-2025-02).
  - failed because: cited prov:composite-inclusion-timing@E2025; answer says 'first full'
- **G3** ✅ *depends* — Probably yes, provided the portfolio is actual and fee-paying. Under the 2025 Edition, every actual, fee-paying, discretionary portfolio must be included in at least one composite. A client-imposed restriction makes a portfolio non-discretionary only where it materially impedes implementation of the strategy. A tobacco exclusion that leaves the portfolio otherwise following the strategy would ordinarily not meet that threshold. Whether it does is a judgement the firm must make and document for this portfolio. If it is not a material impediment, the portfolio stays discretionary and must go into a composite.
- **G4a** ✅ *depends* — Not immediately. Under 3.A.7 portfolios below a documented minimum must not be included, but the guidance says you assess against the minimum at the beginning of each measurement period, so a portfolio above the minimum at the start of the period stays in the composite for that whole period. Whether it must be excluded from the next period depends on how the Board treats temporary breaches caused solely by a significant cash flow. That treatment is set out in Q&A QA-2025-031, which is not among the passages, so check it, along with your documented composite policy, before deciding.
- **G4b** ✅ *depends* — Not necessarily. The general rule is that portfolios below a documented composite minimum must not be included (3.A.7), but where the breach results solely from a significant cash flow, as defined in your documented composite policy, the portfolio may remain in the composite for up to three full measurement periods after the cash flow. This applies only if your documented composite policy provides for this treatment and you document the determination at the time it is made. If the portfolio is still below the minimum at the end of that period, it must be removed. Whether you can retain it therefore depends on whether the 40% withdrawal meets your policy's significant cash flow definition and whether your policy permits this treatment.
- **G5** ✅ *not_covered* — None of the provided passages address staking rewards or digital assets, so their treatment in composite returns cannot be determined from these materials. The passages cover only the definition of a composite, the inclusion of non-fee-paying portfolios, and the timing for adding new portfolios to composites. Consult other sections of the GSB Standards or any guidance on digital assets or return calculation methodology for this question.
- **G6** ✅ *depends* — It depends on the portfolio's characteristics, which the question does not specify. Under both the 2021 and 2025 editions, all actual, fee-paying, discretionary portfolios must be included in at least one composite. Non-fee-paying discretionary portfolios may be included but are not required to be; if they are included, the firm must disclose the percentage of composite assets they represent at each annual period end. If inclusion is required, timing also differs by edition: under the 2025 edition a new portfolio must be added no later than the start of the first full calendar month after it comes under management, and the firm must document the inclusion date. Under the 2021 edition the deadline is the start of the second full calendar month, unless the composite policy specifies an earlier date.
- **G7** ❌ *yes* — Under the current 2025 Edition, a new portfolio must be included in a composite on a timely and consistent basis, and no later than the beginning of the first full calendar month after it comes under management. The firm must also document the inclusion date it applies for each composite. This tightens the 2021 Edition, which allowed up to the beginning of the second full calendar month unless the firm's composite-specific policy set an earlier date. Separately, a new portfolio below a documented composite minimum should not be included (per GS-2025-02).
  - failed because: cited prov:composite-inclusion-timing@E2025; answer says 'first full'
- **G8** ✅ *yes* — Yes. Under 3.A.3, firms must make a description of any composite available to any prospective client on request, and this requirement is identical in both the 2021 and 2025 editions. Relatedly, 3.A.4 (2025) requires firms to document each composite's definition in writing, including inclusion and exclusion criteria, which supports your ability to fulfil such requests.
- **G9** ✅ *yes* — Yes. Non-fee-paying discretionary portfolios may be included in a composite; this permission is unchanged between the 2021 and 2025 editions. If you include them, you must disclose the percentage of composite assets represented by non-fee-paying portfolios as of each annual period end. Inclusion is optional, unlike actual, fee-paying, discretionary portfolios, which must be included in at least one composite. Note that under the 2021 definition, a portfolio subject to your fee schedule counts as fee-paying even if the fee is reduced or waived, so confirm the classification before treating a portfolio as non-fee-paying.
- **G10** ✅ *no* — No, it is not a strict requirement. In both the 2021 and 2025 editions, 3.B.1 states that firms "should not" apply changes to a composite minimum retroactively, which makes it a recommendation rather than a mandatory provision. GS-2025-02 describes the expected practice: a changed minimum applies prospectively from the beginning of the next measurement period, and it refers to 3.B.1 as a recommendation. Following this practice is strongly advised, but the standards do not mandate it.
- **G11a** ❌ *no* — No. Under Amendment 2025-A1, definition 1.D.6 now provides that related-party portfolios (principals, employees, affiliates) whose investment management fees are waived in full are not fee-paying portfolios, so the mandatory inclusion requirement in 3.A.1, which applies only to fee-paying discretionary portfolios, no longer captures them. Such accounts may still be included voluntarily under 3.A.2 as non-fee-paying discretionary portfolios, in which case the firm must disclose the percentage of composite assets they represent as of each annual period end. Note that this applies only where fees are waived in full; partially reduced fees still leave the portfolio fee-paying and subject to 3.A.1.
  - failed because: cited def:fee-paying-portfolio@E2025-A1; conclusion 'no'
- **G11b** ✅ *no* — No. Under Amendment 2025-A1, definition 1.D.6 now provides that related-party portfolios (principals, employees, affiliates) whose investment management fees are waived in full are not fee-paying portfolios, so the mandatory inclusion requirement in 3.A.1, which applies only to fee-paying discretionary portfolios, no longer captures them. Such accounts may still be included voluntarily under 3.A.2 as non-fee-paying discretionary portfolios, in which case the firm must disclose the percentage of composite assets they represent as of each annual period end. Note that this applies only where fees are waived in full; partially reduced fees still leave the portfolio fee-paying and subject to 3.A.1.

## Intake evals

- **M1** ✅ as_of=None facts={}
- **M2** ✅ jurisdiction=None facts={}
- **M3** ✅ unresolved=["withdrawal date: 'last month' (no anchor date given)", 'composite minimum: amount not specified']
- **M4** ✅ facts={'client restriction': 'no tobacco stocks', 'portfolio otherwise follows the strategy': 'yes'} missing=[]
- **M5** ✅ missing=['whether the portfolio is discretionary', 'whether the portfolio is fee-paying', "the portfolio's investment mandate, strategy or objective (to match it to a composite)"]
