# CLAUDE.md — build conventions for this repository

This file is read by any Claude Code session working in this repo (cloud or local). It
carries the working agreement so no chat has to re-establish it.

## What this is

A proof of concept for a **verifiable regulatory knowledge layer**: a layer between a
standards body's guidance and its AI systems that makes answers reliable and verifiable,
not merely retrievable. Submission for a technical challenge: the material is delivered to
the panel in advance (repository, hosted walkthrough, narrated video, PDF), then the author
presents it for 10 minutes and is drilled by a senior technical stakeholder.

**Thesis.** Truth lives in a deterministic, versioned, relationship-aware layer. The LLM
is used only for language — understanding the question and composing the answer — and
nothing reaches the user without a deterministic check against the layer. "The guidance
doesn't cover this" is a first-class answer.

**The line that matters.** A clause can remain word-for-word identical while the correct
answer changes, because a definition, exception, or ruling elsewhere has changed.

## Posture

- **Build mode.** Write real, runnable code with tests. The strategic-advisor persona from
  the surrounding project is suspended inside this repo except for `docs/03-decisions.md`.
- **The author is not a developer.** The rule is: *nothing ships that cannot be explained
  in two sentences.* Prefer the obvious implementation. No clever abstractions, no
  metaprogramming, no framework magic. Small files named for concepts.
- **The spec is `docs/00-corpus-spec.md`.** If code and spec disagree, stop and fix the
  spec first, then the code.
- **The gold set is the spec for behaviour.** `data/gold.yaml` defines what correct
  means. Change it deliberately, in its own commit, with a reason.

## Deliverable mapping (from the brief)

| Brief | Where it lives |
|---|---|
| 01 Architecture + 0→1 | `docs/01-architecture.md` (+ `docs/diagrams/`) |
| 02 Concrete demonstration | `src/`, `data/`, `tests/`, `demo/` — runnable via `docker compose up` |
| 03 Design choices and rationale | `docs/03-decisions.md` (ADR-style; non-obvious decisions first) |
| What is recorded vs. what runs | `docs/04-demonstration.md` (the honesty sheet: hosted site, replay, live, how it was built) |

## Stack (locked)

- Python 3.12 · FastAPI · Pydantic v2 · psycopg 3 with plain SQL (no ORM — the closure query is the system and should read as SQL)
- PostgreSQL 16 + pgvector, via Docker Compose; recursive CTEs for closure
- pytest as the test and eval harness
- LLMs: Anthropic `claude-opus-5-5` composes, `claude-sonnet-5-5` judges and parses
  intake; configurable by env. OpenAI `text-embedding-3-small` for embeddings.
- All LLM calls go through one client module with **record/replay**: tests run from
  fixtures by default; `--live` hits the APIs; `--record` refreshes fixtures.
- UI: one static page (`demo/`), system font stack, no framework, no build step.

## Layout

```
CLAUDE.md
README.md
compose.yaml  Dockerfile  .env.example  pyproject.toml
docs/        00-corpus-spec.md  01-architecture.md  03-decisions.md  04-demonstration.md  eval-report.md  diagrams/
data/
  gold.yaml  the gold set — the specification of correct behaviour, as data
  sources/   prose documents (what the body publishes; what naive RAG chunks)
  graph/     structured seed: nodes.yaml  edges.yaml  documents.yaml  jurisdictions.yaml  issued_answers.yaml
  proposals/ the two bundles that arrive during the demo (Scene B, Scene A)
src/vgl/
  contracts.py   Pydantic models: QueryFrame, Claim, EvidencePacket, Outcome, Answer
  db.py          connection + schema
  seed.py        load data/graph into Postgres; create Release 1
  intake.py      question → QueryFrame (LLM, structured; never infers date/jurisdiction)
  search.py      shortlist (FTS + pgvector, RRF) then choose_entries (LLM, validated against shortlist)
  pipeline.py    ask(): intake → shortlist → choose → resolve → compose → verify (+judge)
  closure.py     deterministic as-of, per-jurisdiction traversal → EvidencePacket
  compose.py     EvidencePacket → structured claims (LLM)
  verify.py      rules V1–V6 + judge → Outcome
  releases.py    proposals, impact preview, publish, release pinning
  naive.py       the baseline: chunk → embed → top-k → answer
  llm.py         single client with record/replay
  api.py         FastAPI app; serves demo/
tests/
  conftest.py    --live / --record / --repeat; tests run against <db>_test, never the demo db
  unit/          closure, verify, releases — deterministic, exact expectations
  eval/          test_gold.py, test_baseline.py (records, never asserts), test_intake.py,
                 expectations.py, report.py (writes docs/eval-report.md)
  fixtures/      recorded model responses (llm/*.json) and embeddings.json
demo/            index.html  app.js  styles.css
```

## Rules

1. **No real regulation.** Every clause, body, jurisdiction, and client is fictional.
   Never paste text from a real standard. Never make a claim about a real standard.
2. **Never commit secrets.** `.env` is gitignored; `gitleaks` runs as a pre-commit hook.
3. **Determinism first.** `closure.py` and `verify.py` import nothing from `llm.py`.
4. **Provenance on every edge.** No edge without `asserted_by`, `basis`, `release_id`.
5. **Every module starts with a plain-English docstring** that explains what it does and
   why it exists, in words the author can repeat under questioning.
6. **Commits are part of Deliverable 03.** Small, meaningful commits with messages that
   state the decision, not the diff.

## Commands

```
docker compose up --build          # Postgres + API + UI at http://localhost:8000
VGL_LLM_MODE=replay docker compose up --build   # the same, with no API keys (recorded model responses)
docker compose run --rm app pytest # unit + eval (replay mode)
docker compose run --rm app pytest tests/eval --live --repeat 5   # evals against real APIs
docker compose run --rm app python -m vgl.seed         # reseed to Release 1 (or POST /api/reset)
# without Docker, from the repo root with a local Postgres:
.venv/bin/python -m vgl.seed && .venv/bin/uvicorn vgl.api:app --port 8000
```

## Status

- [x] Spec drafted and signed off (`docs/00-corpus-spec.md`)
- [x] Schema + seed + Release 1
- [x] Closure + unit tests
- [x] Contracts + intake + compose + verify
- [x] Gold set + baseline + eval report
- [x] Releases: proposals, impact preview, publish
- [x] Demo UI
- [x] docs 01 and 03, diagram
- [x] Verified on the author's Mac with Docker (Nov 4: live G1 call end to end)
- [x] Drill prep (kept outside the repo)
- [x] Keyless replay path (`VGL_LLM_MODE=replay`), verified end to end on a fresh database
- [x] Hosted walkthrough at https://ericediger.com/vgl (recorded output; 9 sections, 47 steps)
- [x] `docs/04-demonstration.md` — what is recorded, what runs, how it was built
- [x] Narrated video over the walkthrough (seven minutes; on Vercel Blob; linked from ericediger.com/vgl/review, the walkthrough's closing frame and README "Start here")
- [x] PDF walkthrough, `docs/vgl-walkthrough.pdf` (11 pages, Letter landscape; regenerate with `python docs/pdf/render.py`)
- [ ] Reviewer access: GitHub invites and/or a zip of `main`; cover email

## Things that bit once

- PyYAML parses unquoted `yes`/`no` as booleans — quote them in `gold.yaml`.
- The structured-output API rejects `minItems`/`maxItems` on arrays; say it in the description.
- Retrieval ties must be broken deterministically (identical texts across editions have
  identical embeddings), or the rerank prompt — and therefore the replay key — drifts.
- `git add -A` will happily commit an agent worktree under `.claude/`; it is ignored now.
