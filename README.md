# Verifiable Guidance Layer

A proof of concept for a **verifiable regulatory knowledge layer** — the layer between a
standards body's authoritative guidance and the AI systems that answer questions about it.

> A clause can remain word-for-word identical while the correct answer changes, because a
> definition, exception, or ruling elsewhere has changed.

Retrieval finds relevant text. This layer answers a different question: *does the text
that was found actually support the conclusion, for this jurisdiction, on this date, given
everything else that modifies it?* It does that by keeping truth in a deterministic,
versioned, relationship-aware graph, using the LLM only for language, and verifying every
composed claim against the graph before anything reaches the user. "The guidance doesn't
cover this" is a first-class answer.

## Status

**Specification stage.** See [`docs/00-corpus-spec.md`](docs/00-corpus-spec.md) — the
fictional corpus, its deliberate traps, the outcome contract, the gold set, and the demo
script. Code follows the spec, not the other way round.

## Deliverables

| | Brief requirement | Location |
|---|---|---|
| 01 | Architecture for a PoC, and 0→1 | `docs/01-architecture.md` *(pending)* |
| 02 | Something concrete | `src/`, `data/`, `tests/`, `demo/` *(pending)* |
| 03 | Design choices and rationale | `docs/03-decisions.md` *(pending)* |

## Running it

```
cp .env.example .env     # add ANTHROPIC_API_KEY and OPENAI_API_KEY
docker compose up --build
open http://localhost:8000
```

*(Compose files land with the first code commit.)*

## Working conventions

See [`CLAUDE.md`](CLAUDE.md).
