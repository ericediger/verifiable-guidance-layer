# 00 · Corpus Specification

**Status:** Draft for sign-off. This document is the spec. Every seed record, gold-set
question, verifier rule, screen, and demo beat derives from it. Nothing in `src/` should
exist without a line here that justifies it.

The corpus is **entirely fictional**. The *Global Standards Board* does not exist, and no
text here is copied from or makes claims about any real standard. The structure is
modelled on how a global standards body typically publishes: numbered provisions with a
required/recommended split, periodic editions that amend and renumber, a separate
definitions section, an interpretive layer of guidance statements and Q&As, and local
adoption by jurisdiction.

---

## 1. The world

### 1.1 The body and the standard

**Global Standards Board (GSB)** publishes the **GSB Standards** for investment
performance presentation. Firms claim compliance with the Standards; compliance
professionals and verifiers interpret them.

Provisions are numbered `section.tier.n`:

| Tier | Meaning | Example |
|---|---|---|
| `A` | Requirement — "must" | `3.A.6` |
| `B` | Recommendation — "should" | `3.B.1` |
| `D` | Definition (Section 1 only) | `1.D.5` |

### 1.2 Editions

| Edition | Published | Effective (GLOBAL) | Notes |
|---|---|---|---|
| **Edition 2021** | 2020-06-30 | 2021-01-01 | Baseline |
| **Edition 2025** | 2024-06-30 | 2025-01-01 | Amends several provisions and definitions; **renumbers** Section 3 by inserting two new provisions |
| **Amendment 2025-A1** | *published live during the demo* | 2026-12-01 | Narrows the definition of *fee-paying portfolio* |

Every clause has a **stable concept ID** that survives editions and renumbering
(`prov:composite-inclusion-timing`) and a **version ID** per edition
(`prov:composite-inclusion-timing@E2025`). The number a human sees (`3.A.4`, `3.A.6`) is a
per-version **display reference**, never an identity.

### 1.3 Jurisdictions

| Code | Name | Adoption behaviour |
|---|---|---|
| `GLOBAL` | Global baseline | Editions effective on GSB dates |
| `JN` | Jurisdiction North | Adopts each edition on the GSB effective date |
| `JS` | Jurisdiction South | Edition 2021 on 2021-01-01; **Edition 2025 adopted effective 2026-01-01** (JS Adoption Notice 2024-11) |

A question is always resolved for one jurisdiction and one as-of date. The UI exposes both
as explicit controls; the intake model never infers them.

### 1.4 Authority tiers

| Tier | Contents | Effect on an answer |
|---|---|---|
| **Authoritative** | Edition provisions and definitions | Can ground a claim |
| **Interpretive** | Guidance Statements, Q&A rulings | Can ground a claim; always surfaced with its label; can modify or carve out an authoritative clause |
| **Practitioner** | Practice notes contributed by practitioners, reviewed by an editor | Never grounds a claim; surfaced as a labelled note alongside the answer |

---

## 2. Sources (prose documents)

Each source exists as a Markdown document under `data/sources/`. These are what the
organisation "publishes", what naive RAG chunks, and what the structured graph was
"extracted" from. The same documents feed both systems so the comparison is fair.

| Source ID | Title | Tier | Effective |
|---|---|---|---|
| `doc:E2021` | GSB Standards, Edition 2021 | Authoritative | 2021-01-01 |
| `doc:E2025` | GSB Standards, Edition 2025 | Authoritative | 2025-01-01 |
| `doc:GS-2025-02` | Guidance Statement on Composite Minimums | Interpretive | 2025-03-01 |
| `doc:QA-2025-031` | Q&A: Temporary breach of a composite minimum following a significant cash flow | Interpretive | 2025-04-15 — **absent from Release 1** |
| `doc:A1` | Amendment 2025-A1 to the Definitions | Authoritative | 2026-12-01 — **published live in Scene A** |
| `doc:JS-AN-2024-11` | JS Adoption Notice 2024-11 | Authoritative (jurisdictional) | 2024-11-15 |
| `doc:PN-001` | Practice note: inclusion-timing policy wording in JS | Practitioner | 2025-05-20 |

---

## 3. Clauses

### 3.1 Section 1 — Definitions

| Concept ID | E2021 ref | E2025 ref | Text (E2021) | Text (E2025) |
|---|---|---|---|---|
| `def:composite` | 1.D.1 | 1.D.1 | A composite is an aggregation of one or more portfolios managed according to a similar investment mandate, objective, or strategy. | *unchanged* |
| `def:discretionary-portfolio` | 1.D.4 | **1.D.5** | A portfolio is discretionary when the firm has sole authority to implement its intended investment strategy. A portfolio subject to client-imposed restrictions is non-discretionary. | A portfolio is discretionary when the firm has sufficient authority to implement its intended investment strategy. Client-imposed restrictions render a portfolio non-discretionary only where they materially impede implementation of the strategy. Firms must document the basis for each such determination. |
| `def:fee-paying-portfolio` | 1.D.5 | **1.D.6** | A fee-paying portfolio is one that is subject to the firm's investment management fee schedule, whether or not the fee is paid directly from the portfolio and whether or not the fee is reduced or waived in whole or in part. | *unchanged* |
| `def:significant-cash-flow` | 1.D.9 | **1.D.11** | A significant cash flow is a client-directed external cash flow of a size, defined in the firm's documented policy for the composite, that would temporarily prevent the firm from implementing the composite strategy. | *unchanged* |

**Amendment 2025-A1** (effective 2026-12-01) creates `def:fee-paying-portfolio@E2025-A1`:

> A fee-paying portfolio is one that is subject to the firm's investment management fee
> schedule, whether or not the fee is paid directly from the portfolio and whether or not
> the fee is reduced in part. **Portfolios of related parties for which all investment
> management fees are waived in full are not fee-paying portfolios.**

### 3.2 Section 3 — Composite Construction

| Concept ID | E2021 ref | E2025 ref | Text |
|---|---|---|---|
| `prov:composite-inclusion-all-discretionary` | 3.A.1 | 3.A.1 | All actual, fee-paying, discretionary portfolios must be included in at least one composite. *(identical in both editions)* |
| `prov:non-fee-paying-inclusion` | 3.A.2 | 3.A.2 | Non-fee-paying discretionary portfolios may be included in a composite. Where included, the firm must disclose the percentage of composite assets represented by non-fee-paying portfolios as of each annual period end. |
| `prov:composite-description-on-request` | 3.A.3 | 3.A.3 | Firms must make a description of any composite available to any prospective client on request. |
| `prov:composite-definition-documented` | — | **3.A.4** *(new)* | Firms must document the definition of each composite in writing, including the criteria for inclusion and exclusion of portfolios. |
| `prov:terminated-portfolio-inclusion` | — | **3.A.5** *(new)* | Terminated portfolios must be included in the historical performance of the composite through the last full measurement period under management. |
| `prov:composite-inclusion-timing` | 3.A.4 | **3.A.6** | **E2021:** New portfolios must be included in a composite on a timely and consistent basis, and no later than the beginning of the **second** full calendar month after the portfolio comes under management, unless the composite-specific policy documented by the firm specifies an earlier date. **E2025:** New portfolios must be included in a composite on a timely and consistent basis, and no later than the beginning of the **first** full calendar month after the portfolio comes under management. Firms must document the inclusion date applied for each composite. |
| `prov:composite-minimum` | 3.A.5 | **3.A.7** | If a firm sets a minimum asset level for portfolios to be included in a composite, the firm must not include portfolios below that minimum. Any such minimum must be documented and applied consistently. *(identical in both editions)* |
| `prov:composite-minimum-no-retroactive-change` | 3.B.1 | 3.B.1 | Firms should not apply changes to a composite minimum retroactively. |

Structured parameters (machine-checkable) attached to versions:

| Version | Parameter | Value |
|---|---|---|
| `prov:composite-inclusion-timing@E2021` | `inclusion_deadline_months` | 2 |
| `prov:composite-inclusion-timing@E2025` | `inclusion_deadline_months` | 1 |
| `ruling:QA-2025-031@v1` | `grace_period_months` | 3 |

### 3.3 Interpretive layer

**`gs:GS-2025-02@v1` — Guidance Statement on Composite Minimums** (Interpretive, effective
2025-03-01; `INTERPRETS` → `prov:composite-minimum@E2025`)

> Provision 3.A.7 requires that portfolios below a documented composite minimum not be
> included in the composite. Firms should assess each portfolio against the minimum at
> the beginning of each measurement period, using the valuation methodology documented in
> the composite policy. Where a portfolio falls below the minimum solely as a result of a
> significant cash flow, the Board has addressed the treatment of such temporary breaches
> in **Q&A QA-2025-031**.

The final sentence creates a `REFERENCES` edge to `ruling:QA-2025-031`. In **Release 1**
the target is an **unresolved reference**: the system knows the ruling exists and is
relevant, but does not hold its text. That is a known gap, not an unknown one.

**`ruling:QA-2025-031@v1` — Temporary breach of a composite minimum following a significant
cash flow** (Interpretive, effective 2025-04-15; `CARVES_OUT` → `prov:composite-minimum@E2025`;
`DEPENDS_ON_DEFINITION` → `def:significant-cash-flow`). **Ingested in Scene B → Release 2.**

> **Question.** Must a portfolio be removed from a composite when it falls below the
> composite minimum solely because of a significant cash flow?
>
> **Answer.** No. Where the breach results solely from a significant cash flow, as defined
> in the firm's documented policy for the composite, the portfolio may remain in the
> composite for up to three full measurement periods following the cash flow, provided
> that the firm's documented composite policy provides for this treatment and the
> determination is documented at the time it is made. If the portfolio remains below the
> minimum at the end of that period, it must be removed.

### 3.4 Practitioner layer

**`note:PN-001@v1`** (Practitioner; author "Senior verifier, JS" (anonymised); 2025-05-20;
reviewed and published by an editor; `ANNOTATES` → `prov:composite-inclusion-timing`;
scope `JS`)

> JS examiners expect the composite policy to state the specific inclusion month. Policies
> using "as soon as practicable" drew findings in 2024 examinations.

Surfaced, labelled, on any JS answer touching inclusion timing. Never grounds a claim.

### 3.5 Issued answers (seeded)

**`ia:IA-0001`** — issued 2025-03-10 under Release 1, to *Harbor Point Advisors* (client
ref `HPA-77`), jurisdiction `JN`, as-of 2025-03-10.

> **Q.** Are employee accounts with fully waived management fees fee-paying portfolios
> that must be included in a composite?
> **A.** ANSWER — Yes. Under 1.D.6 (Edition 2025) a portfolio is fee-paying when it is
> subject to the firm's fee schedule, whether or not the fee is reduced or waived, so such
> accounts are fee-paying and 3.A.1 requires their inclusion.
> **Cites:** `prov:composite-inclusion-all-discretionary@E2025`, `def:fee-paying-portfolio@E2025`

Correct when issued. **Becomes stale on 2026-12-01** when Amendment 2025-A1 takes effect.
Scene A makes the system say so, with the client reference.

---

## 4. Graph model

### 4.1 Node kinds

`clause_version` (provisions and definitions), `guidance_version`, `ruling_version`,
`practice_note`, `document`, `jurisdiction`, `release`, `issued_answer`, `proposal`.

Every versioned node carries: `concept_id`, `version_id`, `display_ref`, `tier`,
`obligation` (`must` / `should` / `definition` / `n/a`), `effective_from`, `effective_to`
(nullable), `text`, `parameters` (JSON, optional), `source_doc`, `status`
(`published` / `unresolved` / `proposed`), `release_id`.

### 4.2 Edge kinds

| Edge | From → To | Meaning |
|---|---|---|
| `DEPENDS_ON_DEFINITION` | clause → definition concept | The clause's meaning depends on this definition |
| `REFERENCES` | version → concept | Explicit cross-reference in the text |
| `SUPERSEDED_BY` | version → version | A later version of the same concept |
| `AMENDED_BY` | version → document | The amending instrument |
| `INTERPRETED_BY` | clause → guidance/ruling | Interpretive material that applies |
| `CARVED_OUT_BY` | clause → ruling | An exception that modifies the clause's effect |
| `ADOPTED_IN` | edition document → jurisdiction | With `effective_from` per jurisdiction |
| `ANNOTATED_BY` | clause → practice note | Practitioner-tier note |
| `CITES` | issued answer → version | The exact versions the answer relied on |

**Every edge carries provenance:** `asserted_by` (person or extractor), `basis`
(`source_text` / `editorial` / `proposal`), `source_passage`, `reviewed_by`,
`release_id`. Nothing links two nodes without someone or something accountable for it.

### 4.3 Resolution rule (deterministic)

Given `(question_frame, jurisdiction, as_of)`:

1. Entry points from hybrid search (keyword + vector) over published versions.
2. For each entry concept, select the version **in force** for `jurisdiction` at `as_of`:
   the edition adopted in that jurisdiction whose jurisdictional effective date ≤ `as_of`,
   and the version with `effective_from ≤ as_of < effective_to`.
3. Follow `DEPENDS_ON_DEFINITION`, `INTERPRETED_BY`, `CARVED_OUT_BY`, `REFERENCES`,
   `ANNOTATED_BY` (scoped to jurisdiction), selecting versions by the same rule, to a
   bounded depth.
4. Any `REFERENCES` whose target is `unresolved` is recorded as a **gap**.
5. Output an **evidence packet**: nodes, edges, gaps, and the release ID.

Same inputs and release ⇒ byte-identical evidence packet.

---

## 5. Releases

A **release** is an immutable snapshot of the published graph. Answers pin to a release.

| Release | Contents | Created |
|---|---|---|
| **R1** | Everything in §3 except `ruling:QA-2025-031` (unresolved reference only) and Amendment 2025-A1 | Seed |
| **R2** | R1 + `ruling:QA-2025-031` and its edges | Scene B, live |
| **R3** | R2 + Amendment 2025-A1 (`def:fee-paying-portfolio@E2025-A1`) | Scene A, live |

---

## 6. Outcome contract

| Outcome | Meaning | Remedy |
|---|---|---|
| `ANSWER` | Grounded, verified, no modifiers outstanding | — |
| `ANSWER_WITH_FLAGS` | Grounded and verified; a modifier (carve-out, pending adoption, upcoming amendment) or a practitioner note is attached | Read the flags |
| `CLARIFY` | A required case fact is missing from the question | Ask the user |
| `REVIEW` | No coverage, an unresolved reference in the closure, or a hard verification failure | Route to a human; log the gap |

Verifier rules (deterministic, hard-fail → `REVIEW` or claim removal):

- V1 Every claim cites ≥ 1 node.
- V2 Every cited node is in the evidence packet (no outside knowledge).
- V3 Every cited node is in force at `as_of` in `jurisdiction` (no stale citations).
- V4 Every `CARVED_OUT_BY` / `INTERPRETED_BY` node in the packet is either cited or flagged.
- V5 Any gap in the packet ⇒ `REVIEW` unless the gap is provably outside the question's scope.
- V6 Practitioner-tier nodes may appear only as flags, never as claim grounding.

Soft check (LLM judge, different model from the composer): does each claim faithfully
reflect the text of the nodes it cites? Disagreement ⇒ flag, not fail.

---

## 7. Gold set

All as-of 2025-06-01 and Release 1 unless stated. "Naive" is the baseline: chunk all
sources → embed → top-k → answer, no dates, no graph, no verifier.

| ID | Jurisdiction | Question | Expected outcome | Must cite | Must not cite | Naive expected |
|---|---|---|---|---|---|---|
| **G1** Stale | JN | By when must a new portfolio be added to a composite? | `ANSWER` — first full month | `prov:composite-inclusion-timing@E2025` | `…@E2021` | Cites E2021 or blends |
| **G2** Jurisdiction | JS | *(same as G1)* | `ANSWER_WITH_FLAGS` — second full month; flag: Edition 2025 adopted in JS from 2026-01-01; PN-001 surfaced | `…@E2021` | `…@E2025` | Answers globally |
| **G3** Interaction | JN | A client bars us from buying tobacco stocks; the portfolio otherwise follows the strategy. Must it be in a composite? | `ANSWER` — yes | `prov:composite-inclusion-all-discretionary@E2025`, `def:discretionary-portfolio@E2025` | `def:discretionary-portfolio@E2021` | Applies the old definition → "not required" |
| **G4a** Carve-out, R1 | JN | A client withdrew 40% last month and the portfolio is now below our composite minimum. Must we remove it? | `REVIEW` — unresolved reference `ruling:QA-2025-031` | `prov:composite-minimum@E2025`, `gs:GS-2025-02@v1` | — | "Yes, remove it" |
| **G4b** Carve-out, R2 | JN | *(identical facts)* | `ANSWER_WITH_FLAGS` — may remain up to 3 months if solely due to a significant cash flow and policy provides for it | `prov:composite-minimum@E2025`, `ruling:QA-2025-031@v1` | — | "Yes, remove it" or misses the condition |
| **G5** Coverage | JN | How are staking rewards on digital assets treated in composite returns? | `REVIEW` — no coverage | — | anything | Fabricates |
| **G6** Clarify | — | Does this portfolio need to be in a composite? | `CLARIFY` — discretionary? fee-paying? jurisdiction? as-of? | — | — | Answers anyway |
| **G7** Historical as-of | JN, as-of 2024-06-01 | *(same as G1)* | `ANSWER` — second full month | `…@E2021` | `…@E2025` | Mixed |
| **G8** Straightforward | JN | Must we provide a composite description if a prospect asks? | `ANSWER` — yes | `prov:composite-description-on-request@E2025` | — | Correct |
| **G9** Straightforward | JN | Can we include non-fee-paying portfolios in a composite? | `ANSWER` — yes, with annual disclosure of the percentage | `prov:non-fee-paying-inclusion@E2025` | — | Correct |
| **G10** Obligation tier | JN | Are we required to avoid changing a composite minimum retroactively? | `ANSWER` — not required; recommended (3.B.1) | `prov:composite-minimum-no-retroactive-change@E2025` | — | Often says "required" |
| **G11a** Scene A, before | JN, as-of 2026-11-15, R3 | Employee accounts with fully waived fees — must they be in a composite? | `ANSWER_WITH_FLAGS` — yes; flag: amendment effective 2026-12-01 changes this | `def:fee-paying-portfolio@E2025` | `…@E2025-A1` | — |
| **G11b** Scene A, after | JN, as-of 2026-12-15, R3 | *(same)* | `ANSWER` — no, not fee-paying under 1.D.6 as amended | `def:fee-paying-portfolio@E2025-A1` | `…@E2025` | — |

### 7.1 Intake evals (query-understanding stage)

| ID | Input | Expected frame |
|---|---|---|
| **M1** | Question with no date | `as_of = null` — never today, never invented |
| **M2** | Question with no jurisdiction | `jurisdiction = null` |
| **M3** | "A client withdrew money last month…" with no anchor date | `event_date = unresolved("last month")` |
| **M4** | G3's question | `case_facts = {client_restriction: true, strategy_impeded: false}` |

### 7.2 Metrics reported

- **Grounded-claim rate** — claims citing ≥ 1 in-packet node / all claims.
- **Stale-citation rate** — must be 0 after verification.
- **Modifier-surfaced rate** — carve-outs / pending adoptions / amendments reflected when present in the packet.
- **Abstention precision / recall** — `REVIEW`+`CLARIFY` issued when warranted, and only then.
- **Closure recall** — seeded dependencies present in the packet / seeded dependencies.
- **Baseline failure rate** — naive wrong-or-unsafe answers over `--repeat N` runs, per gold question.
- **Composer sensitivity** — the matrix above with Opus vs. Sonnet composing. Expectation: stale-citation rate 0 in both; fluency and flag rate differ.

---

## 8. Demo script

1. **The traps** (R1). G1, G3, G4a side by side with naive. Thirty seconds each.
2. **Scene B — the system learns.** G4a returns `REVIEW` naming the gap. Proposal for
   `QA-2025-031` arrives. Editor screen: passage, proposed edges, provenance, tier,
   impact preview (G4 flips; no issued answers affected). Approve → R2. Re-ask → `ANSWER_WITH_FLAGS`.
   Open R1 → still `REVIEW`.
3. **Scene A — the regulation changes.** Publish Amendment 2025-A1. Impact preview: 3.A.1,
   two gold cases, and `IA-0001` with the client reference. Approve → R3. `IA-0001` shows
   "becomes stale 2026-12-01 — re-review."
4. **Jurisdiction.** G2: same question as G1, different answer, practitioner note labelled.
5. **The tests.** Run the suite; show the eval report; point at the baseline failure rates.

The drill question the two scenes answer: *"Did the regulation change, or did your system
learn something it should already have known?"* — Scene A, Scene B, release history.

---

## 9. What the editor sees (Scene B proposal screen)

- The proposed source text, in full.
- Proposed edges, each as a sentence: "GS-2025-02 **references** QA-2025-031"; "3.A.7 is
  **carved out by** QA-2025-031."
- Provenance: proposer, basis, link to the (fictional) GSB Q&A database entry.
- Tier assignment (Interpretive) and effective date (2025-04-15).
- **Impact preview:** gold cases whose outcome would change (`G4: REVIEW → ANSWER_WITH_FLAGS`);
  issued answers affected (none); nodes touched.
- Approve (creates a release with a changelog) / Reject (with reason, kept on record).

---

## 10. Open questions for sign-off

1. Does the world read as credible to a standards-body audience without imitating any
   real standard?
2. G3 and Scene A are both definition-driven on purpose — one in retrieval, one in
   propagation. Keep both, or swap one for a different mechanism?
3. Stretch, if time allows: a `JS` local overlay (a notice making JS stricter than GSB on
   one point before 2025) to show a true local override rather than only delayed adoption.
