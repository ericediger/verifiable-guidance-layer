"""The contracts: typed shapes that every stage hands to the next.

Why it exists: the boundaries between stages are the architecture. A question
becomes a QueryFrame; the resolver turns a frame into an EvidencePacket; the composer
turns a packet into Claims; the verifier turns claims plus packet into an Answer with
an Outcome. Each of these is a plain data shape that can be logged, stored, diffed,
and handed to an agent as JSON. Nothing here calls anything.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

Outcome = Literal["ANSWER", "ANSWER_WITH_FLAGS", "CLARIFY", "REVIEW"]
Tier = Literal["authoritative", "interpretive", "practitioner"]
Role = Literal["entry", "definition", "interpretation", "carve_out", "annotation", "reference"]


# ── intake ───────────────────────────────────────────────────────────────────────

class QueryFrame(BaseModel):
    """What the question is asking, in structured form.

    Jurisdiction and as-of are *inputs the user sets*, never inferred by the model.
    The intake model's job is to extract topics and case facts, and to say plainly
    which facts it could not find rather than guessing them.
    """

    question: str
    jurisdiction: str | None = None
    as_of: dt.date | None = None
    topics: list[str] = Field(default_factory=list, description="short search phrases")
    question_type: Literal[
        "requirement", "permissibility", "timing", "definition", "interaction", "other"
    ] = "other"
    case_facts: dict[str, Any] = Field(default_factory=dict)
    unresolved: list[str] = Field(
        default_factory=list,
        description="facts mentioned but not determinable, e.g. 'event_date: last month (no anchor)'",
    )
    missing_required: list[str] = Field(
        default_factory=list,
        description="facts the question needs before it can be answered",
    )


# ── evidence ─────────────────────────────────────────────────────────────────────

class ResolvedNode(BaseModel):
    version_id: str
    concept_id: str
    kind: str
    title: str
    display_ref: str | None
    tier: Tier
    obligation: str
    text: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_doc: str
    source_title: str
    effective_from: dt.date
    in_force_from: dt.date
    jurisdiction_scope: str | None = None
    role: Role
    depth: int
    via: str | None = None
    from_concept: str | None = None


class EdgeUsed(BaseModel):
    kind: str
    from_concept: str
    to_concept: str
    asserted_by: str
    basis: str
    source_passage: str | None = None
    reviewed_by: str | None = None


class Gap(BaseModel):
    """A concept the closure reached but could not resolve to text in force."""

    concept_id: str
    title: str
    kind: str
    reason: Literal["unresolved_reference", "not_yet_in_force"]
    referenced_from: str
    via: str
    next_in_force_from: dt.date | None = None


class Upcoming(BaseModel):
    """A version of a packet concept that takes effect after the as-of date."""

    concept_id: str
    version_id: str
    display_ref: str | None
    source_doc: str
    source_title: str
    effective_from: dt.date
    in_force_from: dt.date
    replaces_version_id: str | None = None
    text_changed: bool = True

    def is_adoption_delay(self, as_of: dt.date) -> bool:
        """Already effective globally, not yet adopted in this jurisdiction."""
        return self.effective_from <= as_of < self.in_force_from


class Superseded(BaseModel):
    """An earlier version of a packet concept — what the answer would have cited before."""

    concept_id: str
    version_id: str
    display_ref: str | None
    source_doc: str
    in_force_from: dt.date
    in_force_until: dt.date
    text_changed: bool = True


class EvidencePacket(BaseModel):
    """Everything the composer is allowed to know, and everything the verifier checks against."""

    release_id: int
    jurisdiction: str
    as_of: dt.date
    entry_concepts: list[str]
    nodes: list[ResolvedNode]
    edges: list[EdgeUsed]
    gaps: list[Gap]
    upcoming: list[Upcoming]
    superseded: list[Superseded]

    def version_ids(self) -> set[str]:
        return {n.version_id for n in self.nodes}

    def by_version(self, version_id: str) -> ResolvedNode | None:
        for n in self.nodes:
            if n.version_id == version_id:
                return n
        return None

    def groundable_version_ids(self) -> set[str]:
        """Versions a claim may cite: anything that is not practitioner tier."""
        return {n.version_id for n in self.nodes if n.tier != "practitioner"}


# ── composition ──────────────────────────────────────────────────────────────────

class Claim(BaseModel):
    text: str
    cites: list[str] = Field(default_factory=list, description="version_ids this claim rests on")
    kind: Literal["conclusion", "requirement", "condition", "caveat"] = "requirement"


class Composition(BaseModel):
    """The composer's output: a short answer plus the claims that support it."""

    summary: str
    conclusion: Literal["yes", "no", "depends", "not_covered"]
    claims: list[Claim]


# ── verification ─────────────────────────────────────────────────────────────────

class Check(BaseModel):
    rule: str
    passed: bool
    detail: str


class Flag(BaseModel):
    kind: Literal[
        "carve_out", "pending_adoption", "upcoming_amendment", "practitioner_note",
        "unresolved_reference", "judge_disagreement", "recommendation_not_requirement",
        "claim_removed",
    ]
    message: str
    version_id: str | None = None
    concept_id: str | None = None


class Verification(BaseModel):
    checks: list[Check]
    stale_citations: list[str] = Field(default_factory=list)
    ungrounded_claims: list[int] = Field(default_factory=list)
    removed_claims: list[Claim] = Field(default_factory=list)
    judge: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


# ── the answer ───────────────────────────────────────────────────────────────────

class Answer(BaseModel):
    outcome: Outcome
    summary: str
    conclusion: Literal["yes", "no", "depends", "not_covered"] | None = None
    claims: list[Claim]
    flags: list[Flag]
    clarifications: list[str] = Field(default_factory=list)
    frame: QueryFrame
    packet: EvidencePacket | None
    verification: Verification | None
    release_id: int
    composer_model: str | None = None

    @property
    def cited_nodes(self) -> set[str]:
        return {v for c in self.claims for v in c.cites}

    @property
    def flag_kinds(self) -> set[str]:
        return {f.kind for f in self.flags}
