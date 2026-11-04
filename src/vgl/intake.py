"""Intake: turn a question in plain language into a QueryFrame.

The model extracts what the question is about (search topics), what kind of question
it is, and the facts of the case it states. It is told, in so many words, never to
guess a date or a jurisdiction — those are controls the user sets — and to say
plainly which facts are missing rather than fill them in. A valid JSON frame that
invents a fact is a failure, and the intake evals test exactly that.
"""

from __future__ import annotations

import datetime as dt

from vgl.config import settings
from vgl.contracts import QueryFrame
from vgl.llm import LLM, llm as default_llm

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "topics": {
            "type": "array", "items": {"type": "string"},
            "description": "Short search phrases in the vocabulary of the standards (e.g. 'composite inclusion timing', 'discretionary portfolio definition').",
        },
        "question_type": {
            "type": "string",
            "enum": ["requirement", "permissibility", "timing", "definition", "interaction", "other"],
        },
        "case_facts": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"fact": {"type": "string"}, "value": {"type": "string"}},
                "required": ["fact", "value"],
            },
            "description": "Facts about the specific situation that the question states. Only what is stated.",
        },
        "unresolved": {
            "type": "array", "items": {"type": "string"},
            "description": "Things the question mentions that cannot be pinned down from the text alone, e.g. 'event date: \"last month\" (no anchor date given)'.",
        },
        "missing_required": {
            "type": "array", "items": {"type": "string"},
            "description": "Facts about the specific case that the answer turns on and the question does not give. Empty for general questions about what a rule requires.",
        },
    },
    "required": ["topics", "question_type", "case_facts", "unresolved", "missing_required"],
}

SYSTEM = """You prepare compliance questions about investment performance standards for a retrieval system.

Your output is a structured frame, not an answer. Rules:

1. Never infer a jurisdiction or an as-of date. They are set separately by the user. Do not mention them in case_facts.
2. case_facts contains only facts the question states about a specific situation (e.g. "client restriction: no tobacco stocks", "withdrawal: 40% of assets", "portfolio below composite minimum: yes"). Do not add assumptions.
3. unresolved lists things mentioned that cannot be determined from the text alone — relative dates with no anchor ("last month", "recently"), unnamed documents, ambiguous terms.
4. missing_required is for questions about a SPECIFIC portfolio, account or transaction where the answer depends on a fact the question does not give — for example, whether a portfolio is discretionary or fee-paying when asking if it must be in a composite. For GENERAL questions about what a rule requires ("by when must new portfolios be included?"), it is empty.
5. topics are 1–3 short search phrases naming the provision or concept the question is PRIMARILY about, using the vocabulary of the standards (composite, discretionary, fee-paying, inclusion timing, minimum asset level, significant cash flow, terminated portfolio, composite description). The first topic is the main subject. Do not list every concept that might be tangentially relevant.
6. missing_required is strict: list a fact only if, without it, NO answer can be given at all. If the question gives enough to answer conditionally ("if X then…"), leave it empty — the answer will state the condition. A question that gives specific facts about a situation almost always has an empty missing_required.

Examples:
- "Do we have to keep a terminated account in the composite's history?" → topics ["terminated portfolio composite history"], question_type requirement, case_facts [], unresolved [], missing_required [].
- "A pension client told us last year to avoid defence stocks. Is their account discretionary?" → topics ["discretionary portfolio definition"], question_type definition, case_facts [{fact: "client restriction", value: "no defence stocks"}], unresolved ["restriction date: 'last year' (no anchor)"], missing_required [] (the answer can state the condition: discretionary unless the restriction materially impedes the strategy).
- "A client took out a large sum and the account dropped under our composite floor. Do we have to take it out of the composite?" → topics ["composite minimum asset level", "significant cash flow"], question_type requirement, case_facts [{fact: "withdrawal", value: "large sum"}, {fact: "portfolio below composite minimum", value: "yes"}], unresolved ["withdrawal size and date not specified"], missing_required [].
- "Is this account fee-paying?" → topics ["fee-paying portfolio definition"], question_type definition, case_facts [], unresolved [], missing_required ["whether the account is subject to the firm's fee schedule"]."""


def parse(question: str, *, jurisdiction: str | None, as_of: dt.date | None,
          llm: LLM = default_llm, model: str | None = None) -> QueryFrame:
    out = llm.complete_json(
        model=model or settings.intake_model,
        system=SYSTEM,
        user=f"Question:\n{question.strip()}",
        schema=SCHEMA,
        schema_name="query_frame",
        max_tokens=800,
    )
    facts = {f["fact"]: f["value"] for f in out.get("case_facts", [])}
    return QueryFrame(
        question=question.strip(),
        jurisdiction=jurisdiction,
        as_of=as_of,
        topics=[t.strip() for t in out.get("topics", []) if t.strip()],
        question_type=out.get("question_type", "other"),
        case_facts=facts,
        unresolved=list(out.get("unresolved", [])),
        missing_required=list(out.get("missing_required", [])),
    )


def missing_controls(frame: QueryFrame) -> list[str]:
    """The two facts the model is never allowed to supply, checked by code."""
    missing = []
    if not frame.jurisdiction:
        missing.append("jurisdiction")
    if not frame.as_of:
        missing.append("as-of date")
    return missing
