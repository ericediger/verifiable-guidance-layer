# 03 · Design decisions and their rationale

A decision log. Each entry: what was chosen, what was considered and rejected, why, what it
costs, and what I would do with more time. The decisions that were not obvious come first.
The commit history is the second half of this document: each commit message states a
decision, not a diff.

---

## 1. No graph database

**Chose:** Postgres 16 with explicit `concepts`, `nodes`, `edges` tables; recursive CTEs for
traversal; pgvector for embeddings in the same store.

**Considered:** Neo4j (the instinct the problem shape invites); a triple store; Postgres
with relationships buried in JSON.

**Why:** The two graph operations the product needs — "follow the required relationships
for this case" and "what depends on this changed clause" — are shallow (≤ 4 hops) and
bounded. A recursive CTE over an indexed edge table handles them in milliseconds at this
scale and in low hundreds of milliseconds at millions of edges. One store for text, vectors,
edges, releases and audit is one thing to operate, back up, and explain. And the schema
*already is* a property graph, so the door to a graph store stays open: nodes and typed
edges export mechanically.

**Costs:** Pattern queries across the whole graph and graph algorithms (centrality to
prioritise editorial review) will eventually want a graph engine. Switch triggers: p95
traversal latency failing despite indexing, whole-graph pattern queries, or team fluency.

**With more time:** A read-only projection into a graph store for editorial exploration,
with Postgres remaining the system of record.

## 2. "In force" is computed, never stored — and a release is a watermark

**Chose:** A version carries only its effective date (and the jurisdiction's adoption date
for its source document). The version in force on a date is selected at query time: the
visible version with the latest jurisdiction-adjusted start on or before the date. A
release is a pair of columns on every row (`created_release`, `retired_release`), not a
copy of anything.

**Considered:** Stored `effective_to` columns updated when a successor arrives; snapshot
copies per release; event sourcing.

**Why:** Stored end dates are the classic source of silent inconsistency, and updating them
when a successor arrives *mutates rows that earlier releases depend on*. Computing in-force
means adding a version in release N+1 closes the previous one in N+1 only; release N is
byte-identical forever, which is what makes "open the release this answer was given under
and it reproduces" true rather than aspirational. Watermarks give that for free; copies
would multiply storage and invite drift.

**Costs:** Effective dates must be right at ingestion; a wrong date is a wrong answer. Hard
deletes are forbidden. Explicit withdrawal without replacement needs an `effective_to`,
which exists for that case only.

**With more time:** Edge validity windows (an edge that holds only for some versions), and
a bitemporal "known since" on versions for the transaction-time questions a release only
approximates.

## 3. Verification is a separate, deterministic pass with a graded failure contract

**Chose:** Six rules in plain code over the evidence packet. A bad *supporting* claim is
removed and flagged; a bad *conclusion* fails the answer to REVIEW. Flags are derived from
the packet (carve-outs, pending adoptions, upcoming amendments, practitioner notes) so the
user sees them whether or not the composer chose to mention them. `verify.py` and
`closure.py` import nothing from the model client — a rule, enforced by reading imports.

**Considered:** Prompting the composer harder; an LLM judge as the gate; verification
folded into composition via self-critique.

**Why:** The brief's failure is confident wrong answers. A gate that is itself probabilistic
cannot be the answer to that. The rules are small, exact, and testable without the thing
they gate — twelve unit tests hand the verifier compositions a model might write (stale,
invented, uncited, over-reaching) and no model is involved. The judge exists, but as a
second, different model asked a narrow question whose only power is to add a soft flag.

**Costs:** Rules only know what the packet knows. V3 (no stale citations) turned out never to
fire in the evals, because the packet never offers a superseded version as evidence; it stays
as defence in depth against a future composer with a longer context or a formatting bug.

**With more time:** A faithfulness check that is structural rather than model-based for the
claim types that permit it (numeric parameters, dates).

## 4. Known gaps are first-class; a reference the graph cannot resolve withholds finality

**Chose:** When a source references material the graph does not hold, the concept is
registered with no versions. The resolver reports it as a gap; V5 turns the answer into
REVIEW with the gap named; the composer is told the material exists and is not held.

**Considered:** Ignoring unresolvable references; answering with a generic caveat.

**Why:** This is the difference between a *known* gap (a reference it can't resolve) and an
*unknown* one (coverage it has no idea it lacks). Only the first is detectable, and
detecting it converts the brief's third failure — the unknown carve-out — from a confident
wrong answer into a routed review with a specific thing to go and find. It is also what
makes the practitioner contribution loop concrete: the proposal that closes the gap is the
demo's Scene B.

**Costs:** Over-reporting if extraction registers references liberally; mitigated by
distinguishing "not held" from "not yet in force", which is a flag, not a REVIEW.

## 5. Clarify only when a specific-case question gives no facts; otherwise answer conditionally

**Chose:** CLARIFY fires in code when a control (jurisdiction, as-of) is missing, or when the
intake marks facts as required *and* the question stated no case facts at all. A question
that gives facts is answered, with the conditions as verified claims and the unstated facts
listed "to confirm".

**Considered:** CLARIFY whenever any determinative fact is missing (the first live run did
this and turned two good questions into forms).

**Why:** A compliance officer prefers "yes, if the restriction does not materially impede
the strategy — and you must document that determination" to a questionnaire. The conditions
are claims, cited, and verified like any other. The intake model is also told, with
examples, that `missing_required` is strict; the code rule is the backstop.

**Costs:** A question that gives one irrelevant fact and omits the determinative one gets a
conditional answer rather than a prompt. Acceptable, and visible in the "to confirm" list.

## 6. Entry selection is a shortlist plus a model choosing from titles — not a threshold

**Chose:** Hybrid search (Postgres full-text + pgvector, reciprocal rank fusion) produces up
to eight candidates for recall. A small model call picks one to three entry concepts from
their *titles*. The choice is validated in code against the shortlist: the model can narrow,
never add. Nothing chosen → REVIEW.

**Considered:** Cosine thresholds tuned to this corpus; top-k by fused score; letting the
composer see everything the search found.

**Why:** The first live run showed the right concepts winning on similarity by hundredths —
0.544 vs 0.536 vs noise at 0.513 — in a small, dense corpus. Thresholds that separate those
would not survive a real corpus. A rerank step is standard, cheap, explainable ("it chooses
from the table of contents"), and keeps every probabilistic choice upstream of the
deterministic closure. The alternative — letting a long guidance statement that mentions
every keyword into every packet — dragged its unresolved reference into unrelated questions
and turned them into REVIEW.

**Costs:** One more model call (about a second). A question that lands on the wrong provision
produces a correct answer about the wrong provision; the failure is visible in the packet,
not hidden.

## 7. Practitioner knowledge has a home and a ceiling

**Chose:** A third authority tier. Practice notes attach to clauses by edge, scoped to a
jurisdiction, surfaced with their label on every relevant answer, and never able to ground
a claim (V6). Authoritative text is append-only. *Everything* — rulings, amendments, notes —
enters through the same proposal → impact preview → editor → release path.

**Considered:** Letting practitioners edit the graph; a free-text comments field; merging
notes into clause text.

**Why:** The brief's problem is an AI that silently merges material of different authority.
Letting a practitioner write directly into the graph recreates it with a different author.
Tiering preserves the value of institutional knowledge, keeps it visibly distinct, and gives
the publisher an answer to "who changed this interpretation and why".

**Costs:** A review workflow needs reviewers. The PoC has one editor identity.

## 8. Impact preview by simulation, not by static analysis

**Chose:** Load the proposal's bundle inside a savepoint as release N+1, re-resolve every
gold case, walk the graph backwards for dependents, compute which issued answers would
expire and when, then roll back.

**Considered:** Computing affected concepts from the bundle's edges alone.

**Why:** Simulation is exact and uses the same resolver the product uses. It is also the
sentence that lands best with people who care about testing: the impact preview *is the
test suite, run against a change that does not exist yet*. Static analysis would miss
version-selection effects (an amendment that changes which version a case resolves to
without touching any edge).

**Costs:** Proportional to the gold set. At thousands of cases, preview becomes a batch job
over the cases whose entry concepts are in the dependency set — which the reverse walk
already computes.

## 9. A synthetic corpus shaped like a real standards body

**Chose:** A fictional Global Standards Board with GIPS-shaped structure: numbered provisions
with a required/recommended split, editions that amend *and renumber*, a definitions section
provisions depend on, guidance statements and Q&As as the interpretive layer, jurisdictional
adoption on a delay. Nothing copied; no claim about any real standard.

**Considered:** Real regulation (a narrow, verifiable example such as a settlement-cycle
change was tempting).

**Why:** Four reasons, in order. Correctness risk is the brief's own failure mode: assert
something about real regulation to an audience that knows it, and the exercise is over.
Controllability: the demo needs a known amendment, a known cross-standard dependency, a
known carve-out, with clean dates. Licensing. And drill drift — the conversation becomes
"is that reading of Reg X right?" rather than architecture.

**Costs:** Every number in the eval report is a statement about this corpus.

**With more time:** One real public-domain excerpt through an extraction sketch, to show
the ingestion path on real prose without making claims about its meaning.

## 10. A fair baseline, and baseline tests that record rather than assert

**Chose:** The naive baseline chunks the *same* prose the graph was extracted from, retrieves
top-k by the same embeddings, and answers with the *same* composer model. Baseline tests
record what it did; they do not assert that it fails.

**Why:** The comparison should isolate the layer, not the model. And a baseline that happens
to get a question right is a data point, not a broken test. The honest finding is the
useful one: with a frontier model and a small corpus, naive RAG gets most ordinary
questions right; it fails every case where the right answer is not the newest text applied everywhere, now — a different place, a past date, an amendment not yet in force — and cannot say which.

**With more time:** `--repeat N` in live mode already turns pass/fail into a rate per case;
a composer-sensitivity matrix (Opus vs Sonnet composing) is a config switch away and was
cut for Friday.

## 11. One door to the models, with record/replay

**Chose:** A single client module. Every call is keyed by its full request; `replay` serves
the recording and fails loudly if there is none; `record` refreshes. Structured outputs use
the API's native JSON-schema mode, so responses conform by construction.

**Why:** Evals that need the network and spend money on every run are evals nobody runs. The
same suite is deterministic in CI and live on demand with one flag. A side effect that
mattered: replay exposed that the retrieval shortlist had non-deterministic tie-breaks
(identical texts across editions have identical embeddings), so an identical question could
produce a different rerank prompt. That was a correctness bug, not a testing convenience.

## 12. Models and vendors

**Chose:** Opus composes; Sonnet judges and parses intake; OpenAI `text-embedding-3-small`
truncated to 256 dimensions for embeddings. All configurable by environment.

**Why:** Cost was not a constraint for the PoC, and composition quality is visible in the
demo. A *different* model as judge is a cheap independence argument. Truncated embeddings
keep fixtures small; retrieval here is a recall problem. Multi-vendor is deliberate: the
architecture does not depend on any one of them.

**At scale:** route by question complexity; cache resolved packets; note that the closure
bounds the context to the relevant subgraph rather than top-k chunks of whole documents,
which is a cost argument for the architecture itself.

## 13. Python, FastAPI, plain SQL — and code a non-developer can defend

**Chose:** Python 3.12, FastAPI, Pydantic, psycopg with SQL in strings, pytest. Modules named
for concepts; a plain-English docstring on every one; no ORM, no clever abstractions.

**Why:** The workload is I/O-bound model calls and SQL; the heavy lifting is in Postgres and
the models. Python's eval and data tooling is the strongest available and pytest is the
lingua franca any reviewer reads. Plain SQL because the recursive closure *is* the system
and should be readable as SQL by anyone who asks to see it. The contracts are the schema,
the JSON answer shape, and the HTTP API — Python is an implementation detail behind them.

## 14. The repository is the deliverable

**Chose:** Spec first (`docs/00-corpus-spec.md`, commit one), then code that follows it, in
small commits whose messages state decisions. The gold set is data. The eval report is
generated.

**Why:** A reviewer who opens the history sees the design unfold, including the corrections
below. That is more convincing than a document that pretends the design arrived finished.

---

## What the first live run changed

Four corrections, all surfaced by running the real thing rather than reasoning about it:

1. **Retrieval drift.** Intake produced five topics; the vector query was diluted by them. Fix:
   embed the question alone, weight the vector leg, and add the rerank step (decision 6).
2. **Intake over-asked.** Every fact that would *refine* an answer was listed as required.
   Fix: decision 5.
3. **Role by path, not by edge.** A ruling the rerank chose as an entry point was labelled
   "entry" rather than "carve-out", so its flag was not raised. Fix: a ruling's role follows
   the edge that points at it, and a ruling asked about directly is resolved together with
   the clause it modifies.
4. **A flaw in the fiction.** Under the pre-amendment definition of a fee-paying portfolio as
   first written ("receives compensation"), a fully fee-waived account was already *not*
   fee-paying — so the amendment flipped nothing. The composer read the text correctly and
   exposed the problem. Fix: the corpus, not the model.

## With more time, in priority order

1. **Extraction.** Model-assisted structuring of prose into concepts, versions and edges with
   provenance, entering through the proposal path — then one real public-domain document
   through it.
2. **Judge meta-evaluation.** A few dozen human labels on claim/citation pairs to measure the
   judge's own precision and recall before trusting its flags in a UI.
3. **Composer-sensitivity matrix** across models, to show in numbers that correctness comes
   from the layer and fluency from the model.
4. **Jurisdictional override** (a place stricter than the global baseline), edge validity
   windows, and true bitemporal "known since" on versions.
5. **Editorial roles and an audit view**: who proposed, who approved, what changed, for every
   release — the data is already there.
6. **Agent surface**: the existing response wrapped as an MCP tool, with the outcome contract
   as the tool's schema.
