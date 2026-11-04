"""The API: the layer as a service, and the demo UI that sits on it.

Every endpoint returns the same typed shapes the pipeline uses internally, so the
JSON an agent receives is exactly what the UI renders: an Answer with its outcome,
claims, citations, flags, evidence packet and verification. The editorial endpoints
expose proposals, impact preview and publication; the issued-answers endpoint
exposes staleness.

On first start against an empty database, the service seeds Release 1.
"""

from __future__ import annotations

import datetime as dt
import logging
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from vgl import closure, db, naive, pipeline, releases, seed
from vgl.config import settings
from vgl.contracts import QueryFrame
from vgl.llm import FixtureMissing

log = logging.getLogger("vgl")


def _ensure_seeded() -> None:
    with db.connection() as conn:
        has_tables = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'releases'"
        ).fetchone()
        if has_tables and conn.execute("SELECT count(*) AS n FROM releases").fetchone()["n"] > 0:
            return
        log.info("empty database — seeding Release 1")
        _seed(conn)


def _seed(conn: psycopg.Connection) -> None:
    try:
        seed.seed(conn, embed=True, quiet=True)
    except (FixtureMissing, RuntimeError) as e:
        log.warning("seeded without embeddings (%s); keyword search only", e)
        conn.rollback()
        seed.seed(conn, embed=False, quiet=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_seeded()
    yield


app = FastAPI(title="Verifiable Guidance Layer", version="0.1.0", lifespan=lifespan)


# ── request shapes ───────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    jurisdiction: str | None = None
    as_of: dt.date | None = None
    release_id: int | None = None
    compare_naive: bool = False
    use_judge: bool = True
    composer_model: str | None = None
    frame: QueryFrame | None = Field(default=None, description="Supply a frame to skip model intake (manual facts path).")


class ResolveRequest(BaseModel):
    entry_concepts: list[str]
    jurisdiction: str
    as_of: dt.date
    release_id: int | None = None


class DecisionRequest(BaseModel):
    decided_by: str = "editor:a.okafor"
    note: str = ""


# ── answering ────────────────────────────────────────────────────────────────────

@app.post("/api/ask")
def ask(req: AskRequest) -> dict[str, Any]:
    with db.connection() as conn:
        answer = pipeline.ask(
            conn, req.question, jurisdiction=req.jurisdiction, as_of=req.as_of, release_id=req.release_id,
            frame=req.frame, use_judge=req.use_judge, composer_model=req.composer_model,
        )
        out: dict[str, Any] = {"answer": answer.model_dump(mode="json")}
        if req.compare_naive:
            try:
                out["naive"] = naive.ask_naive(conn, req.question, answer.release_id).model_dump(mode="json")
            except Exception as e:  # the baseline is a comparison, never a dependency
                out["naive"] = {"error": str(e)}
        return out


@app.post("/api/resolve")
def resolve(req: ResolveRequest) -> dict[str, Any]:
    """The deterministic core alone: entry concepts in, evidence packet out. No model."""
    with db.connection() as conn:
        packet = closure.resolve(conn, req.entry_concepts, req.jurisdiction, req.as_of, req.release_id)
        return packet.model_dump(mode="json")


# ── reading the graph ────────────────────────────────────────────────────────────

@app.get("/api/releases")
def list_releases() -> list[dict]:
    with db.connection() as conn:
        return _json(releases.list_releases(conn))


@app.get("/api/jurisdictions")
def list_jurisdictions() -> list[dict]:
    with db.connection() as conn:
        return [dict(r) for r in conn.execute("SELECT code, name FROM jurisdictions ORDER BY code")]


@app.get("/api/gold")
def gold() -> list[dict]:
    return _json(releases.load_gold())


@app.get("/api/graph")
def graph(release_id: int | None = None) -> dict[str, Any]:
    """Concepts and edges visible in a release, for the visualisation."""
    with db.connection() as conn:
        r = release_id if release_id is not None else closure.current_release(conn)
        vis = "(x.created_release <= %(r)s AND (x.retired_release IS NULL OR x.retired_release > %(r)s))"
        concepts = conn.execute(
            f"""SELECT c.concept_id, c.kind, c.title,
                       (SELECT count(*) FROM nodes x WHERE x.concept_id = c.concept_id AND {vis}) AS versions
                FROM concepts c WHERE c.created_release <= %(r)s ORDER BY c.kind, c.concept_id""",
            {"r": r},
        ).fetchall()
        edges = conn.execute(
            f"SELECT x.kind, x.from_concept, x.to_concept, x.asserted_by, x.basis FROM edges x WHERE {vis} ORDER BY x.id",
            {"r": r},
        ).fetchall()
        return {"release_id": r, "concepts": [dict(c) for c in concepts], "edges": [dict(e) for e in edges]}


@app.get("/api/concepts/{concept_id:path}")
def concept_history(concept_id: str, release_id: int | None = None) -> dict[str, Any]:
    with db.connection() as conn:
        r = release_id if release_id is not None else closure.current_release(conn)
        c = conn.execute("SELECT * FROM concepts WHERE concept_id = %s", (concept_id,)).fetchone()
        if c is None:
            raise HTTPException(404, f"unknown concept {concept_id}")
        versions = conn.execute(
            """SELECT n.version_id, n.display_ref, n.tier, n.obligation, n.text, n.parameters, n.source_doc,
                      d.title AS source_title, n.effective_from, n.jurisdiction_scope, n.created_release
               FROM nodes n JOIN documents d ON d.id = n.source_doc
               WHERE n.concept_id = %s AND n.created_release <= %s
                 AND (n.retired_release IS NULL OR n.retired_release > %s)
               ORDER BY n.effective_from""",
            (concept_id, r, r),
        ).fetchall()
        return _json({"concept": dict(c), "release_id": r, "versions": [dict(v) for v in versions]})


# ── editorial workflow ───────────────────────────────────────────────────────────

@app.get("/api/proposals")
def list_proposals() -> list[dict]:
    with db.connection() as conn:
        return _json(releases.list_proposals(conn))


@app.get("/api/proposals/{proposal_id:path}/impact")
def proposal_impact(proposal_id: str) -> dict[str, Any]:
    with db.connection() as conn:
        try:
            return _json(releases.impact_preview(conn, proposal_id))
        except KeyError:
            raise HTTPException(404, f"unknown proposal {proposal_id}")


@app.get("/api/proposals/{proposal_id:path}")
def get_proposal(proposal_id: str) -> dict[str, Any]:
    with db.connection() as conn:
        try:
            return _json(releases.get_proposal(conn, proposal_id))
        except KeyError:
            raise HTTPException(404, f"unknown proposal {proposal_id}")


@app.post("/api/proposals/{proposal_id:path}/approve")
def approve_proposal(proposal_id: str, req: DecisionRequest) -> dict[str, Any]:
    with db.connection() as conn:
        try:
            r = releases.approve(conn, proposal_id, req.decided_by, req.note)
        except KeyError:
            raise HTTPException(404, f"unknown proposal {proposal_id}")
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"release_id": r}


@app.post("/api/proposals/{proposal_id:path}/reject")
def reject_proposal(proposal_id: str, req: DecisionRequest) -> dict[str, Any]:
    with db.connection() as conn:
        try:
            releases.reject(conn, proposal_id, req.decided_by, req.note)
        except KeyError:
            raise HTTPException(404, f"unknown proposal {proposal_id}")
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"status": "rejected"}


@app.get("/api/issued-answers")
def issued_answers(release_id: int | None = None) -> list[dict]:
    with db.connection() as conn:
        return _json(releases.list_issued_answers(conn, release_id))


@app.post("/api/reset")
def reset() -> dict[str, Any]:
    """Back to Release 1. For the demo."""
    with db.connection() as conn:
        _seed(conn)
        return {"release_id": closure.current_release(conn)}


@app.get("/api/health")
def health() -> dict[str, Any]:
    with db.connection() as conn:
        r = closure.current_release(conn)
        embedded = conn.execute("SELECT count(*) AS n FROM nodes WHERE embedding IS NOT NULL").fetchone()["n"]
    return {"ok": True, "release_id": r, "embedded_nodes": embedded, "llm_mode": settings.llm_mode,
            "composer_model": settings.composer_model, "judge_model": settings.judge_model}


# ── the demo page ────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.demo_dir / "index.html")


if settings.demo_dir.exists():
    app.mount("/demo", StaticFiles(directory=settings.demo_dir), name="demo")


def _json(obj: Any) -> Any:
    """Make dates and other non-JSON types serialisable."""
    if isinstance(obj, dict):
        return {k: _json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json(v) for v in obj]
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return obj
