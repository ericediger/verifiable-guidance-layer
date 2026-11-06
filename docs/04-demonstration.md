# 04 · The demonstration: what is recorded, what runs, and how it was built

This document is for a reviewer who wants to know exactly what they are looking at. There
are two things to look at — a hosted walkthrough and this repository — and they are not the
same kind of thing. The first is a presentation of recorded output. The second is the
system. Everything claimed about the system is checkable in the second.

---

## 1. The hosted walkthrough

**[ericediger.com/vgl](https://ericediger.com/vgl)** is a static, keyboard-driven
presentation in nine sections and forty-seven steps. It shows **recorded output of the real
system** — nothing on the site calls a model or a database.

Where the output came from: on 4 November 2026 the full pipeline in this repository was run
live — `claude-opus-5-5` composing, `claude-sonnet-5-5` judging and parsing intake, OpenAI
`text-embedding-3-small` embedding — against Release 1, then Release 2 (after approving the
Q&A proposal), then Release 3 (after approving the amendment). The responses, impact previews,
issued-answer states, graph and eval report were saved as JSON
(`answers_release1.json`, `answers_release2.json`, `answers_release3.json`,
`impact_preview_*.json`, `issued_answers_*.json`, `graph_release3.json`, `eval-report.json`).
The site renders those files.

**What is simulated on the site — and only this:**

- **Latency.** The "Ask" progress bar is a 2.5-second animation. Live, a question takes
  10–25 seconds, almost all of it two model calls (compose, judge) plus two small ones
  (intake, choose entries); the deterministic resolve step is milliseconds.
- **The release badge.** The bump from Release 1 → 2 → 3 on approval is scripted to the
  moment of the click; the releases themselves, their counts and their changelogs are the
  system's.

**What is not simulated:** every verdict, every claim and its citation, every flag, every
judge note, every impact-preview line, the issued answer's expiry date, the graph the
subgraph views are drawn from, and every number on the evidence section. Each traces to a
file the system wrote. The eval numbers are the same ones in
[`docs/eval-report.md`](eval-report.md) in this repository.

## 2. The repository

Everything in the repository is functional. Two modes matter to a reviewer:

| | `VGL_LLM_MODE=replay` (no keys) | `VGL_LLM_MODE=live` (keys in `.env`) |
|---|---|---|
| Command | `VGL_LLM_MODE=replay docker compose up --build` | `docker compose up --build` |
| Resolve, verify, releases, impact preview, staleness | Real, identical in both modes — no model is involved in any of them | Same |
| Intake · choose entries · compose · judge | Recorded responses, served from `tests/fixtures/` — the same fixtures the test suite replays | Real API calls |
| Embeddings | Recorded (`tests/fixtures/embeddings.json`) | Real API calls |
| The thirteen gold questions | Work, exactly as worded (the question chips) | Work |
| Any other question, or a reworded one | HTTP 409 with a plain message, shown in the UI | Works |
| The two proposal scenes (Release 1 → 2 → 3), the issued answer that expires, reset to Release 1 | Work | Work |
| `pytest` (59 tests, about 2 seconds) | Default mode | `pytest tests/eval --live` |

The model steps use **one code path** in both modes. `src/vgl/llm.py` is the only module that
talks to a vendor; in `replay` it looks up the recording keyed by the full request and fails
loudly if there is none; in `record` it refreshes the recordings. A reworded question produces
a different request, hence a different key, hence a 409 rather than a wrong answer served from
the wrong recording.

**Capability by surface**

| Capability | Hosted site | Repository, replay | Repository, live |
|---|---|---|---|
| See the thirteen cases answered, with claims, citations, flags and the packet | Yes (recorded) | Yes (recorded model output, live resolve/verify) | Yes |
| Ask a new question | No | No (409) | Yes |
| Change jurisdiction, as-of date or release on a recorded question | No | Only the recorded combinations | Yes |
| Preview a proposal's impact, approve it, see the new release | Shown (recorded) | Yes, computed | Yes, computed |
| Open an earlier release and see the earlier answer reproduce | Shown (recorded) | Yes | Yes |
| See which issued client answer expires, and when | Shown (recorded) | Yes, computed | Yes, computed |
| Compare with the naive baseline | Shown (recorded) | Yes (recorded baseline output) | Yes |
| Run the tests and regenerate the eval report | No | Yes | Yes |
| Read the closure SQL, the verifier rules, the schema | Linked | Yes | Yes |

## 3. How it was built

Two days, in this order, and the commit history shows it:

1. **Spec first.** [`docs/00-corpus-spec.md`](00-corpus-spec.md) was written and committed
   before any code: the fictional corpus, the traps, the outcome contract, the verifier rules
   and the gold set. If code and spec disagree, the spec is fixed first.
2. **The gold set as the behavioural specification.** [`data/gold.yaml`](../data/gold.yaml)
   states, as data, what a correct answer to each question must and must not cite and which
   flags it must raise. The evals assert structural properties — outcome, citations, flags,
   gaps — never prose equality.
3. **The deterministic core with unit tests before any model call.** `closure.py`,
   `verify.py` and `releases.py` were written and tested (28 tests, exact expectations)
   against the seed graph with no model anywhere. They import nothing from `llm.py`; that
   is a rule a reviewer can check by reading the imports.
4. **Record/replay from day one.** Every model call goes through one module and is keyed by
   its full request, so the probabilistic stages are deterministic in tests and the whole
   suite runs with no network.
5. **The baseline recorded, never asserted.** `tests/eval/test_baseline.py` documents what
   ordinary RAG does on the same questions with the same model; it does not assert that the
   baseline fails, and the one place it gets an easy question right is reported as such.
6. **The UI last.** One static page over the same JSON the API returns to an agent.

The structured graph in `data/graph/` was **authored by hand to match the prose** in
`data/sources/`, with provenance recorded on every edge as if produced by an extractor and
reviewed by an editor. Extraction at scale is the largest piece of production work and was
deliberately kept out of a proof of concept ([`03-decisions.md`](03-decisions.md), decision 9
and "with more time").

The code was written by an AI coding agent (Claude Code) working under the author's direction
and a written working agreement, [`CLAUDE.md`](../CLAUDE.md): nothing ships that cannot be
explained in two sentences; no real regulation anywhere; provenance on every edge;
determinism first; commit messages that state a decision, not a diff. The architecture, the
corpus design, the decisions in the log and the scope cuts are the author's. The first live
run changed four things, all recorded in the decision log; the corpus itself was corrected
once when the composer read a definition more carefully than its author had.

## 4. What a public live demo would need

The code needs no change beyond configuration. The work is deployment and guardrails:

- **A hosted Postgres 16 with pgvector** — Neon, Supabase, RDS, or a Fly.io volume.
- **The FastAPI container** on Fly.io, Render, Railway or Cloud Run, behind HTTPS, with the
  two API keys as platform secrets.
- **Spend control.** A monthly cap in both vendor consoles. Each live question is three to
  four model calls, 10–25 seconds on the 4 November run and a few cents (estimate, at current list prices).
- **Access control.** Per-IP rate limits and a shared passcode or SSO in front of `/api/ask`.
- **Reset discipline.** A guard on `/api/reset` and a scheduled nightly reset to Release 1,
  so the proposal scenes are always available to the next visitor.
- **Logging.** Every answer is already stored with its frame, packet and verification in
  the `answers` table; ship those rows to wherever the team reads logs.
- **A status line** in the header showing mode (live / recorded) and release — the demo UI
  already shows the release and a *recorded responses* tag in replay mode.

Estimate: one working day to deploy, assuming an existing cloud account.

## 5. For an implementer

[`01-architecture.md`](01-architecture.md) is the design and the 0 → 1 path;
[`03-decisions.md`](03-decisions.md) is why. What follows is the map.

**Module map** (`src/vgl/`; every file opens with a plain-English docstring):

| Module | One line |
|---|---|
| `contracts.py` | The typed shapes every stage hands to the next: QueryFrame, EvidencePacket, Claim, Answer, Outcome |
| `config.py` | Every environment knob in one place; nothing else reads `os.environ` |
| `db.py` | Open a connection, create or wipe the schema; plain SQL everywhere |
| `schema.sql` | The data model, readable top to bottom: concepts, nodes, edges, releases, adoptions, issued answers, proposals, chunks |
| `seed.py` | Load `data/graph`, `data/sources`, `data/proposals` into Postgres as Release 1; the same insert functions load an approved proposal |
| `intake.py` | Question → QueryFrame (model, structured output); never supplies a date or a place |
| `search.py` | Shortlist (full-text + pgvector, reciprocal rank fusion), then a model chooses entry concepts from titles, validated against the shortlist |
| `closure.py` | **Deterministic.** Entry concepts + jurisdiction + as-of + release → EvidencePacket, including known gaps. Two SQL statements |
| `compose.py` | EvidencePacket → summary and claims bound to version IDs (model); the judge lives here too |
| `verify.py` | **Deterministic.** Rules V1–V6; removes, flags or refuses; derives flags from the packet |
| `releases.py` | Proposals, impact preview (savepoint simulation), approve, reject, issued-answer staleness |
| `naive.py` | The baseline: chunk → embed → top-k → answer, over the same prose with the same model |
| `pipeline.py` | `ask()`: intake → shortlist → choose → resolve → compose → verify (+judge); two early exits (CLARIFY, REVIEW) |
| `llm.py` | The one door to the models: live, replay, record |
| `api.py` | FastAPI: `/api/ask`, `/api/resolve`, releases, proposals and impact, issued answers, reset, health; serves `demo/` |

**Data flow.** A question with its two controls (jurisdiction, as-of date) and a release
becomes a frame; the frame's topics produce a shortlist; a model narrows the shortlist to
entry concepts; the resolver walks the graph from those concepts and selects the version of
each concept in force in that place on that date within that release; the composer writes
claims from the packet only; the verifier checks every claim against the packet and derives
the flags; an optional judge may add a soft note; the Answer — outcome, claims, citations,
flags, packet, verification record, release — is stored and returned. The JSON an agent
receives from `/api/ask` is the JSON the demo page renders. There is no path to an answer
that skips verification.

**The schema in one paragraph.** `concepts` are stable identities that survive editions and
renumbering. `nodes` are their dated versions: display reference, tier, obligation, text,
optional machine-checkable parameters, effective date. `edges` are typed, concept-to-concept
relationships, each carrying who asserted it, on what basis, from which passage, reviewed by
whom. Every row records the release that created it and, if retired, the release that
retired it — a release is a watermark, not a copy. `adoptions` give a jurisdiction its own
effective date for a document. "In force" is never stored: it is the visible version with
the latest jurisdiction-adjusted effective date on or before the as-of date. `issued_answers`
pin what was told to a client to the versions it relied on; `proposals` hold bundles waiting
for an editor; `chunks` hold the same prose for the baseline.

**The eval harness.**

```
pytest                                   # 59 tests: 28 unit, 26 gold/baseline evals, 5 intake; replay; ~2 s
pytest tests/unit                        # the deterministic core alone
pytest tests/eval --live                 # the evals against the real models
pytest tests/eval --live --repeat 5      # rates per case, not pass/fail
pytest tests/eval --record               # refresh the recordings
```

The eval session writes `docs/eval-report.md` and `docs/eval-report.json`. Tests use their
own database (`<name>_test`) and never touch the demo's.

**The 0 → 1 path**, in the order it would be done:

1. **Extraction through the proposal path.** A model-assisted extractor turns prose into
   concepts, versions and edges with provenance, and its output enters the graph only as a
   proposal — through the same impact preview and editor decision as everything else. Then
   one real public-domain document through it.
2. **A real corpus** with its real effective dates and adoption dates, captured with care: a
   wrong date is a wrong answer, and the verifier cannot see it.
3. **Editor tooling and roles**: who proposed, who approved, what changed, per release. The
   data is already there; the view is not.
4. **Authentication**, and tenancy on `answers` and `issued_answers` — never on the graph,
   which belongs to the publisher.
5. **A judge meta-evaluation**: a few dozen human labels on claim/citation pairs, so the
   judge's own precision and recall are known before its notes are trusted in a UI.
6. **Scale**: low millions of versions and tens of millions of edges fit one Postgres with
   read replicas; the closure is at most four hops and indexed both ways. A graph database
   becomes worth it when queries become whole-graph pattern matching, graph algorithms are
   needed, or traversal latency fails despite indexing. The schema already is a property
   graph, so the export is mechanical.

## 6. What to believe, and on what basis

| Claim | Basis |
|---|---|
| The system gives the right answer on every gold case | `pytest` → 13/13; `docs/eval-report.md` |
| No stale citation reaches a user | The packet never offers a superseded version, so 0 of 70 composed citations were to one; V3 would remove any, so the rate after verification is 0 by construction |
| Resolve and verify involve no model | `closure.py` and `verify.py` import nothing from `llm.py`; 28 unit tests run with no model |
| Every claim shown passed the structural checks; the summary did not | The rules and the judge check claims; the one-paragraph summary is the composer's reading of the kept claims. `verify.py` passes it through — a known limit, listed in `01-architecture.md` |
| Release 1 still says REVIEW after Release 2 exists | Releases are watermarks; `tests/unit/test_releases.py` |
| The baseline fails the three cases that depend on when or where | G2, G7, G11a in the eval report, recorded not asserted — and it gets the rest right. It received the question only (no date, no place), as document RAG is usually deployed; a baseline given both in its prompt is the next experiment and has not been run |
| The site shows what the system actually said | Recorded JSON from a live run of this code on 4 November 2026; the same numbers as the committed eval report |
| Every number here is a statement about this corpus | The corpus is fictional and small; nothing here is a claim about any real standard |
