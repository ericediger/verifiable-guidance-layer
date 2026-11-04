"""Compose: write the answer from the evidence packet, and nothing else.

The composer sees exactly what the resolver produced — the versions in force, the
material that interprets or carves them out, the practitioner notes (marked as not
citable), and the references the graph could not resolve (marked as not held). It
returns a one-line summary and a list of atomic claims, each bound to the version
IDs it rests on. The verifier then checks every one of those bindings.

The judge lives here too: a second, different model asked a narrow question — does
each claim follow from the text it cites? — with no access to the question or the
packet beyond those texts. It can raise a flag; it cannot clear one.
"""

from __future__ import annotations

from vgl.config import settings
from vgl.contracts import Claim, Composition, EvidencePacket, QueryFrame
from vgl.llm import LLM, llm as default_llm

COMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string", "description": "One sentence answering the question directly."},
        "conclusion": {"type": "string", "enum": ["yes", "no", "depends", "not_covered"]},
        "claims": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "string"}},
                    "kind": {"type": "string", "enum": ["conclusion", "requirement", "condition", "caveat"]},
                },
                "required": ["text", "cites", "kind"],
            },
        },
    },
    "required": ["summary", "conclusion", "claims"],
}

COMPOSE_SYSTEM = """You draft answers for compliance professionals strictly from the evidence provided.

Rules — these are absolute:
1. Use only the EVIDENCE IN FORCE. Every claim must cite one or more of its version IDs, copied exactly (the text in square brackets). Never cite anything else and never invent an ID.
2. No outside knowledge. If the evidence does not address the question, set conclusion to "not_covered" and say so in one claim citing the closest evidence.
3. The jurisdiction and as-of date are fixed. Answer for that place and that date only. Do not apply or speculate about material described as upcoming or not yet in force.
4. Material marked NOT HELD is a known reference the system does not have the text of. Do not guess its contents. If it is relevant to the question, say in a caveat that it exists and has not been reviewed.
5. Material marked PRACTITIONER NOTE is context only. It cannot be cited and must not be presented as a requirement.
6. Where an exception or carve-out is in the evidence and could apply to the facts given, state the condition under which it applies as a "condition" claim.
7. Write the first claim as the conclusion (kind "conclusion"). Keep every claim short and atomic — one point, one citation set. Use the display reference (e.g. 3.A.6) in the prose and the version ID in cites.
8. Distinguish "must" (requirement) from "should" (recommendation) exactly as the evidence does."""


def _format_packet(packet: EvidencePacket) -> str:
    lines: list[str] = []
    lines.append("EVIDENCE IN FORCE (citable):")
    for n in packet.nodes:
        if n.tier == "practitioner":
            continue
        role = {"entry": "provision", "definition": "definition", "interpretation": "interpretive guidance",
                "carve_out": "EXCEPTION / carve-out", "reference": "referenced material"}[n.role]
        lines.append(f"- [{n.version_id}] {n.display_ref or n.title} — {role}, {n.tier}, "
                     f"obligation: {n.obligation}; {n.source_title}; in force from {n.in_force_from.isoformat()}")
        lines.append(f"    {n.text}")
        if n.parameters:
            lines.append(f"    parameters: {n.parameters}")
    notes = [n for n in packet.nodes if n.tier == "practitioner"]
    if notes:
        lines.append("")
        lines.append("PRACTITIONER NOTES (context only — cannot be cited):")
        for n in notes:
            lines.append(f"- {n.display_ref}: {n.text}")
    if packet.gaps:
        lines.append("")
        lines.append("REFERENCED BUT NOT HELD (do not guess contents):")
        for g in packet.gaps:
            why = "no text held in this release" if g.reason == "unresolved_reference" else \
                  f"not in force until {g.next_in_force_from}"
            lines.append(f"- {g.title} — referenced by {g.referenced_from}; {why}")
    return "\n".join(lines)


def _format_frame(frame: QueryFrame) -> str:
    parts = [f"Question: {frame.question}",
             f"Jurisdiction: {frame.jurisdiction}",
             f"As of: {frame.as_of.isoformat() if frame.as_of else 'unspecified'}"]
    if frame.case_facts:
        parts.append("Facts stated: " + "; ".join(f"{k}: {v}" for k, v in frame.case_facts.items()))
    if frame.unresolved:
        parts.append("Unresolved in the question: " + "; ".join(frame.unresolved))
    return "\n".join(parts)


def compose(frame: QueryFrame, packet: EvidencePacket, *, llm: LLM = default_llm,
            model: str | None = None) -> Composition:
    out = llm.complete_json(
        model=model or settings.composer_model,
        system=COMPOSE_SYSTEM,
        user=_format_frame(frame) + "\n\n" + _format_packet(packet),
        schema=COMPOSE_SCHEMA,
        schema_name="composition",
        max_tokens=1500,
    )
    return Composition(
        summary=out["summary"].strip(),
        conclusion=out["conclusion"],
        claims=[Claim(text=c["text"].strip(), cites=list(c["cites"]), kind=c["kind"]) for c in out["claims"]],
    )


# ── the judge ────────────────────────────────────────────────────────────────────

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "index": {"type": "integer"},
                    "faithful": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["index", "faithful", "reason"],
            },
        }
    },
    "required": ["verdicts"],
}

JUDGE_SYSTEM = """You check whether short claims are faithful to the source texts they cite.

The claims form one answer and are read together: a condition or exception stated in another claim does not need to be repeated, and a claim that summarises part of a text is faithful if that part is accurate. Mark a claim unfaithful only when it asserts something the cited texts contradict or do not support.

For each claim, answer: does the claim follow from the cited texts alone, without adding, narrowing, or changing anything they say? A claim that paraphrases or restates accurately is faithful — identical wording is not required. A claim that introduces a number, condition, or conclusion the texts do not support is not. Each cited text is labelled with its reference (e.g. "3.A.6") and title; a claim may use that label. Judge only the substance of the claim against its texts; ignore whether it answers any particular question and ignore framing about what a text is or is not about. Give a one-sentence reason."""


def make_judge(llm: LLM = default_llm, model: str | None = None):
    """Return a function (claims, packet) -> list of {index, faithful, reason}."""

    def judge(claims: list[Claim], packet: EvidencePacket) -> list[dict]:
        if not claims:
            return []
        blocks = []
        for i, c in enumerate(claims):
            texts = [f"    [{v}] {packet.by_version(v).display_ref} {packet.by_version(v).title}: {packet.by_version(v).text}"
                     for v in c.cites if packet.by_version(v)]
            blocks.append(f"Claim {i}: {c.text}\n  Cited texts:\n" + "\n".join(texts))
        out = llm.complete_json(
            model=model or settings.judge_model,
            system=JUDGE_SYSTEM,
            user="\n\n".join(blocks),
            schema=JUDGE_SCHEMA,
            schema_name="judge_verdicts",
            max_tokens=1200,
        )
        by_index = {v["index"]: v for v in out.get("verdicts", [])}
        return [by_index.get(i, {"index": i, "faithful": True, "reason": "not assessed"}) for i in range(len(claims))]

    return judge
