"""The pipeline: one question in, one verified answer out.

    question ──intake──▶ frame ──search──▶ entry concepts ──resolve──▶ packet
            ──compose──▶ claims ──verify (+judge)──▶ Answer, pinned to a release

Two early exits: CLARIFY when a control (jurisdiction, as-of) or a required case fact
is missing, and REVIEW when nothing in the graph addresses the question. Every answer
is stored with its frame, packet and verification, so it can be audited and, when the
graph changes, re-checked.
"""

from __future__ import annotations

import datetime as dt
import json

import psycopg

from vgl import closure, compose, intake, search, verify
from vgl.config import settings
from vgl.contracts import Answer, QueryFrame
from vgl.llm import LLM, llm as default_llm


def ask(
    conn: psycopg.Connection,
    question: str,
    *,
    jurisdiction: str | None,
    as_of: dt.date | None,
    release_id: int | None = None,
    frame: QueryFrame | None = None,
    use_judge: bool = True,
    store: bool = True,
    llm: LLM = default_llm,
    composer_model: str | None = None,
) -> Answer:
    r = release_id if release_id is not None else closure.current_release(conn)

    # 1. Intake — or a frame supplied directly (the manual-facts path needs no model).
    if frame is None:
        frame = intake.parse(question, jurisdiction=jurisdiction, as_of=as_of, llm=llm)
    else:
        frame = frame.model_copy(update={"jurisdiction": jurisdiction, "as_of": as_of})

    # Controls (jurisdiction, as-of) are always required. Case facts trigger CLARIFY only
    # when the question is about a specific case and gives nothing to work with; when it
    # gives facts, we answer conditionally and the conditions become verified claims.
    missing = intake.missing_controls(frame)
    if frame.missing_required and not frame.case_facts:
        missing += list(frame.missing_required)
    if missing:
        answer = verify.clarify(frame, missing, r)
        return _store(conn, answer, store)

    # 2. Where does the question land? Hybrid search for recall, a small model call for
    #    precision — validated so it can only choose from what the search found.
    candidates = search.shortlist(conn, frame, r, llm=llm)
    entries = search.choose_entries(frame, candidates, llm=llm)
    if not entries:
        answer = verify.no_coverage(frame, None, r)
        return _store(conn, answer, store)

    # 3. Deterministic closure.
    packet = closure.resolve(conn, entries, frame.jurisdiction, frame.as_of, r)
    if not packet.nodes:
        answer = verify.no_coverage(frame, packet, r)
        return _store(conn, answer, store)

    # 4. Compose from the packet, then 5. verify against it.
    model = composer_model or settings.composer_model
    composition = compose.compose(frame, packet, llm=llm, model=model)
    judge = compose.make_judge(llm) if use_judge else None
    answer = verify.verify(frame, packet, composition, judge=judge, composer_model=model)
    answer.clarifications = list(frame.missing_required)   # shown as "facts to confirm"
    return _store(conn, answer, store)


def _store(conn: psycopg.Connection, answer: Answer, store: bool) -> Answer:
    if not store:
        return answer
    conn.execute(
        """INSERT INTO answers (question, frame, jurisdiction, as_of, release_id, outcome, claims, flags, packet,
                                composer_model, verification)
           VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb)""",
        (
            answer.frame.question, answer.frame.model_dump_json(), answer.frame.jurisdiction, answer.frame.as_of,
            answer.release_id, answer.outcome, json.dumps([c.model_dump() for c in answer.claims]),
            json.dumps([f.model_dump() for f in answer.flags]),
            answer.packet.model_dump_json() if answer.packet else "null",
            answer.composer_model,
            answer.verification.model_dump_json() if answer.verification else "null",
        ),
    )
    conn.commit()
    return answer
