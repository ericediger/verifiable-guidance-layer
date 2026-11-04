# Eval report

Generated 2026-11-04T14:29 · mode **replay** · 13 layer runs over 13 gold cases · 13 baseline runs

This file is written by `pytest tests/eval`. It is the evidence for the thesis, produced by the
test suite rather than by hand. See `data/gold.yaml` for what each case requires.

## Metrics

| Metric | Value | Meaning |
|---|---|---|
| Gold pass rate (layer) | 100% | Every expectation met: outcome, citations, flags |
| Grounded-claim rate | 100% | Composed claims that survived verification |
| Stale citations caught | 0 of 70 composed | Removed before reaching the user; rate after verification is 0 by construction |
| Closure recall | 100% | Expected versions present in the evidence packet |
| Modifier surfaced rate | 100% | Carve-outs, pending adoptions, upcoming amendments flagged when present |
| Abstention precision / recall | 100% / 100% | REVIEW/CLARIFY issued when warranted, and only then |
| Judge disagreements | 3 | Soft flags from the independent model; never change a verdict |
| Intake pass rate | 100% | No invented dates or jurisdictions; missing facts named |
| **Baseline failure rate** | **23%** | Naive RAG wrong or unsafe on the same questions, same model |

## Per case

| Case | Trap | Layer outcome | Pass | Cited | Flags | Baseline conclusion | Baseline failed |
|---|---|---|---|---|---|---|---|
| G1 | stale | ANSWER | ✅ | composite@E2025<br>composite-inclusion-timing@E2025 | — | yes | 0/1 |
| G2 | jurisdiction | ANSWER_WITH_FLAGS | ✅ | composite@E2021<br>composite-inclusion-timing@E2021 | pending_adoption, practitioner_note | yes | 1/1 |
| G3 | interaction | ANSWER | ✅ | discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025<br>composite-inclusion-all-discretionary@E2025<br>non-fee-paying-inclusion@E2025 | — | depends | 0/1 |
| G4a | carve_out | REVIEW | ✅ | external-cash-flow@E2025<br>measurement-period@E2025<br>significant-cash-flow@E2025<br>GS-2025-02@v1<br>composite-minimum@E2025 | judge_disagreement, unresolved_reference | depends | 0/1 |
| G4b | carve_out | ANSWER_WITH_FLAGS | ✅ | measurement-period@E2025<br>GS-2025-02@v1<br>composite-minimum@E2025<br>QA-2025-031@v1 | carve_out | depends | 0/1 |
| G5 | coverage | REVIEW | ✅ | gross-of-fees-return@E2025 | — | not_covered | 0/1 |
| G6 | clarify | CLARIFY | ✅ | — | — | depends | 0/1 |
| G7 | stale | ANSWER_WITH_FLAGS | ✅ | composite@E2021<br>composite-inclusion-timing@E2021 | upcoming_amendment | yes | 1/1 |
| G8 | none | ANSWER | ✅ | composite@E2025<br>composite-description-on-request@E2025 | — | yes | 0/1 |
| G9 | none | ANSWER | ✅ | discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025<br>composite-inclusion-all-discretionary@E2025<br>non-fee-paying-inclusion@E2025 | — | yes | 0/1 |
| G10 | obligation | ANSWER_WITH_FLAGS | ✅ | composite@E2025<br>composite-minimum-no-retroactive-change@E2025 | recommendation_not_requirement | no | 0/1 |
| G11a | amendment | ANSWER_WITH_FLAGS | ✅ | discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025<br>composite-inclusion-all-discretionary@E2025<br>non-fee-paying-inclusion@E2025 | judge_disagreement, upcoming_amendment | no | 1/1 |
| G11b | amendment | ANSWER_WITH_FLAGS | ✅ | discretionary-portfolio@E2025<br>fee-paying-portfolio@E2025-A1<br>composite-inclusion-all-discretionary@E2025<br>non-fee-paying-inclusion@E2025 | judge_disagreement | no | 0/1 |

## Baseline answers (what naive RAG said)

- **G1** ✅ *yes* — Under the current GSB Standards (Edition 2025), a new portfolio must be included in a composite on a timely and consistent basis, and no later than the beginning of the first full calendar month after it comes under management; the firm must also document the inclusion date applied for each composite. This replaces the more lenient 2021 rule, which allowed inclusion as late as the beginning of the second full calendar month unless the firm's composite policy specified an earlier date. Separately, a portfolio below a documented composite minimum must not be included at all, so the deadline applies only to portfolios that meet any minimum.
- **G2** ❌ *yes* — Under the current GSB Standards (Edition 2025), a new portfolio must be included in a composite on a timely and consistent basis, and no later than the beginning of the first full calendar month after it comes under management; the firm must also document the inclusion date applied for each composite. This replaces the more lenient 2021 rule, which allowed inclusion as late as the beginning of the second full calendar month unless the firm's composite policy specified an earlier date. Separately, a portfolio below a documented composite minimum must not be included at all, so the deadline applies only to portfolios that meet any minimum.
  - failed because: cited prov:composite-inclusion-timing@E2025; answer says 'first full'
- **G3** ✅ *depends* — Probably yes. A client restriction makes a portfolio non-discretionary only if it materially impedes the firm's ability to implement its intended strategy [5]. If excluding tobacco stocks does not materially impede the strategy, the portfolio stays discretionary, and if it is fee-paying it must be included in at least one composite [1]. Whether the restriction is material depends on the strategy (for example, it is minor for a broad equity mandate but could matter for a consumer-staples or sector-focused one), and you must document the basis for your determination either way [5].
- **G4a** ✅ *depends* — Not immediately. Under 3.A.7 portfolios below a documented composite minimum must not be included, but GS-2025-02 says the test is applied at the beginning of each measurement period, and a portfolio above the minimum at that point stays in the composite for the whole period. So last month's withdrawal does not require removal mid-period. If the portfolio is still below the minimum at the start of the next measurement period, it would generally have to be excluded. However, because the shortfall comes from a significant cash flow, the Board's specific treatment of such temporary breaches is set out in Q&A QA-2025-031, which is not among these passages, so you should check it before deciding.
- **G4b** ✅ *depends* — Not necessarily. Provision 3.A.7 generally prohibits including portfolios below a documented composite minimum, but where the breach results solely from a significant cash flow (as defined in your documented composite policy), the portfolio may remain in the composite for up to three full measurement periods after the cash flow. This applies only if your composite policy provides for this treatment and you document the determination at the time it is made. If the portfolio is still below the minimum at the end of that period, it must be removed; and if your policy does not provide for this treatment, or the 40% withdrawal does not meet your significant cash flow definition, the general rule requiring exclusion applies.
- **G5** ✅ *not_covered* — None of the provided passages address staking rewards or digital assets, so the standards excerpted here do not say how such rewards should be treated in composite returns. The passages cover only the definition of a composite (1.D.1), the inclusion of non-fee-paying portfolios and the related disclosure (3.A.2), and the timing for adding new portfolios to composites (3.A.6 in the 2025 edition, 3.A.4 in the 2021 edition). For guidance on staking income, you would need to consult other sections of the standards or separate guidance on return calculation and income recognition.
- **G6** ✅ *depends* — It depends on the portfolio's characteristics, which the question does not specify. Under both the 2021 and 2025 editions, every actual, fee-paying, discretionary portfolio must be included in at least one composite, while non-fee-paying discretionary portfolios may be included but are not required to be; if they are included, the firm must disclose the percentage of composite assets they represent as of each annual period end. Where inclusion is required, the 2025 edition requires a new portfolio to be added no later than the beginning of the first full calendar month after it comes under management, with the inclusion date documented. The 2021 edition allowed until the second full calendar month, unless the firm's composite policy specified an earlier date.
- **G7** ❌ *yes* — Under the current GSB Standards (Edition 2025), a new portfolio must be included in a composite on a timely and consistent basis, and no later than the beginning of the first full calendar month after it comes under management; the firm must also document the inclusion date applied for each composite. This replaces the more lenient 2021 rule, which allowed inclusion as late as the beginning of the second full calendar month unless the firm's composite policy specified an earlier date. Separately, a portfolio below a documented composite minimum must not be included at all, so the deadline applies only to portfolios that meet any minimum.
  - failed because: cited prov:composite-inclusion-timing@E2025; answer says 'first full'
- **G8** ✅ *yes* — Yes. Under 3.A.3, firms must make a description of any composite available to any prospective client who requests it. This requirement is identical in the 2021 and 2025 editions, so the answer does not depend on which edition applies. Relatedly, the 2025 edition (3.A.4) requires each composite definition, including its inclusion and exclusion criteria, to be documented in writing, which supports your ability to meet such requests.
- **G9** ✅ *yes* — Yes. Under 3.A.2, non-fee-paying discretionary portfolios may be included in a composite; this is unchanged between the 2021 and 2025 editions. If you include them, you must disclose the percentage of composite assets represented by non-fee-paying portfolios as of each annual period end. Inclusion is optional, unlike fee-paying discretionary portfolios, which must be included in at least one composite (3.A.1). Also note that a portfolio whose fee is reduced or waived may still count as fee-paying if it is subject to the firm's fee schedule (2021 definition 1.D.5), so confirm the classification before treating a portfolio as non-fee-paying.
- **G10** ✅ *no* — No, it is not a strict requirement. Under both the 2021 and 2025 editions, provision 3.B.1 says firms "should not" apply changes to a composite minimum retroactively, and GS-2025-02 explicitly calls 3.B.1 a recommendation. Avoiding retroactive changes is therefore recommended best practice rather than a mandatory provision. The guidance expects any change to a composite minimum to apply prospectively from the beginning of the next measurement period, so following that approach is strongly advisable.
- **G11a** ❌ *no* — No, provided the employee accounts are related-party portfolios with all investment management fees waived in full. Amendment 2025-A1 revises definition 1.D.6 so these portfolios are no longer fee-paying, which means the mandatory inclusion rule in 3.A.1 (all actual, fee-paying, discretionary portfolios) does not apply to them. Under the unamended Edition 2025 definition they had to be included. Under 3.A.2 the firm may still choose to include them as non-fee-paying discretionary portfolios, but it must then disclose the percentage of composite assets they represent at each annual period end. Accounts whose fees are only partly reduced remain fee-paying and must still be included.
  - failed because: cited def:fee-paying-portfolio@E2025-A1; conclusion 'no'
- **G11b** ✅ *no* — No, provided the employee accounts are related-party portfolios with all investment management fees waived in full. Amendment 2025-A1 revises definition 1.D.6 so these portfolios are no longer fee-paying, which means the mandatory inclusion rule in 3.A.1 (all actual, fee-paying, discretionary portfolios) does not apply to them. Under the unamended Edition 2025 definition they had to be included. Under 3.A.2 the firm may still choose to include them as non-fee-paying discretionary portfolios, but it must then disclose the percentage of composite assets they represent at each annual period end. Accounts whose fees are only partly reduced remain fee-paying and must still be included.

## Intake evals

- **M1** ✅ as_of=None facts={}
- **M2** ✅ jurisdiction=None facts={}
- **M3** ✅ unresolved=["withdrawal date: 'last month' (no anchor date given)", 'composite minimum: amount not specified']
- **M4** ✅ facts={'client restriction': 'no tobacco stocks', 'portfolio otherwise follows the strategy': 'yes'} missing=[]
- **M5** ✅ missing=['whether the portfolio is discretionary', 'whether the portfolio is fee-paying', "whether the portfolio's strategy matches an existing composite definition"]
