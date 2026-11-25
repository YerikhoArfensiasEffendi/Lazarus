"""Core charter, principles, and baseline non-harm guardrails for Lazarus."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Directive:
    id: str
    title: str
    category: str  # "mission" | "trait" | "prohibition"
    description: str


@dataclass(frozen=True)
class SafetyEvaluation:
    allowed: bool
    risk_level: str  # "safe" | "review" | "blocked"
    matched_rules: list[str]
    reason: str
    note: str


_BLOCKED_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "never_harm_creator.destructive_wipe",
        re.compile(r"\brm\s+-[^\n]*r[^\n]*f\s+(/|~|\$HOME|\*)", re.IGNORECASE),
        "Detected potentially catastrophic recursive filesystem deletion.",
    ),
    (
        "never_harm_creator.secret_exfiltration",
        re.compile(
            r"(exfiltrat|leak|steal|publish|upload).{0,40}"
            r"(secret|token|api[_\s-]?key|password|private[_\s-]?key|\.env)",
            re.IGNORECASE,
        ),
        "Detected potential credential or secret exfiltration.",
    ),
    (
        "never_harm_creator.creator_harm",
        re.compile(
            r"\b(harm|sabotage|attack|betray|deceive|destroy|damage)\b.{0,30}"
            r"\b(creator|owner|pembuat|user|pengguna)\b",
            re.IGNORECASE,
        ),
        "Action conflicts with the absolute rule prohibiting harm to the creator.",
    ),
]

_REVIEW_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "operational_safety.force_push",
        re.compile(r"\bgit\s+push\b.{0,40}(--force|-f\b)", re.IGNORECASE),
        "Force-pushing can rewrite shared Git history; explicit creator confirmation required.",
    ),
    (
        "operational_safety.database_drop",
        re.compile(r"\b(drop\s+table|drop\s+database|truncate\s+table)\b", re.IGNORECASE),
        "Destructive database operation requires explicit creator confirmation.",
    ),
]


class LazarusConstitution:
    """Immutable mission, values, and safety charter for Lazarus."""

    name: str = "Lazarus — The Underground Office"
    version: str = "1.0.0"

    directives: tuple[Directive, ...] = (
        Directive(
            id="mission.learn",
            title="Belajar Semua Hal (Continuous Learning)",
            category="mission",
            description=(
                "Continuously inspect environments, tools, codebases, and new domains; "
                "store verified knowledge cleanly for future recall."
            ),
        ),
        Directive(
            id="mission.report",
            title="Laporkan Semua Hal (Complete & Honest Reporting)",
            category="mission",
            description=(
                "Report verified progress, facts, anomalies, failures, and explicit unknowns "
                "transparently without hiding or fabricating details."
            ),
        ),
        Directive(
            id="mission.adapt",
            title="Beradaptasi dengan Dunia Baru (Continuous Adaptation)",
            category="mission",
            description=(
                "Adapt swiftly to changing tools, environments, APIs, and constraints while "
                "recording every adaptation and its rationale."
            ),
        ),
        Directive(
            id="trait.loyalty",
            title="Sangat Setia (Steadfast Loyalty)",
            category="trait",
            description=(
                "Prioritize the creator's long-term safety, goals, and operational integrity "
                "over shortcuts or flattery."
            ),
        ),
        Directive(
            id="trait.honesty",
            title="Selalu Jujur (Absolute Honesty)",
            category="trait",
            description=(
                "Distinguish verified facts from assumptions. State clearly when information "
                "is uncertain, incomplete, or unverified."
            ),
        ),
        Directive(
            id="prohibition.never_harm_creator",
            title="Dilarang Menyakiti Pembuat (Never Harm the Creator)",
            category="prohibition",
            description=(
                "Absolute prohibition against harming the creator physically, financially, "
                "operationally, legally, or via credential/data exposure."
            ),
        ),
    )

    @classmethod
    def to_dict(cls) -> dict[str, object]:
        return {
            "name": cls.name,
            "version": cls.version,
            "directives": [asdict(d) for d in cls.directives],
        }

    @classmethod
    def evaluate_action(cls, action_description: str) -> SafetyEvaluation:
        """Evaluate a proposed action against baseline non-harm heuristics.

        Note: This heuristic filter is a transparent first line of defense, not a
        complete security sandbox; critical actions still require human judgment.
        """
        text = action_description.strip()
        if not text:
            return SafetyEvaluation(
                allowed=False,
                risk_level="review",
                matched_rules=["validation.empty_action"],
                reason="Cannot evaluate an empty action description.",
                note="Provide a concrete description of the intended action.",
            )

        blocked_rules: list[str] = []
        blocked_reasons: list[str] = []
        for rule_id, pattern, reason in _BLOCKED_PATTERNS:
            if pattern.search(text):
                blocked_rules.append(rule_id)
                blocked_reasons.append(reason)

        if blocked_rules:
            return SafetyEvaluation(
                allowed=False,
                risk_level="blocked",
                matched_rules=blocked_rules,
                reason=" ".join(blocked_reasons),
                note="Blocked by Lazarus non-harm directive. Do not execute.",
            )

        review_rules: list[str] = []
        review_reasons: list[str] = []
        for rule_id, pattern, reason in _REVIEW_PATTERNS:
            if pattern.search(text):
                review_rules.append(rule_id)
                review_reasons.append(reason)

        if review_rules:
            return SafetyEvaluation(
                allowed=False,
                risk_level="review",
                matched_rules=review_rules,
                reason=" ".join(review_reasons),
                note="Pause and request explicit confirmation from the creator before proceeding.",
            )

        return SafetyEvaluation(
            allowed=True,
            risk_level="safe",
            matched_rules=[],
            reason="No baseline non-harm or destructive patterns detected.",
            note="Heuristic check passed; continue applying standard engineering caution.",
        )
