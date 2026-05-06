"""Decision review reminder: decay, stale candidate scan, Feishu-friendly digest (Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass

from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateMetaClass
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore


@dataclass
class DecisionReviewRequest:
    project: str
    limit: int = 3


@dataclass
class DecisionReviewResult:
    """Structured output for cron / CLI (markdown body + rows + decay stats)."""
    markdown: str
    decay_touched: int
    candidates: list[EventCandidateMetaClass]


class DecisionReviewService:
    """Decay pass + list review candidates + markdown / card payloads."""

    def __init__(self, decision_store: DecisionMemoryStore):
        self._store = decision_store

    def run_review(self, request: DecisionReviewRequest) -> DecisionReviewResult:
        decay_n = self._store.decay()
        candidates = self._store.list_review_candidates(
            project=request.project,
            limit=request.limit,
        )
        if not candidates:
            return DecisionReviewResult("", decay_n, [])

        lines = [
            "## Decision Review",
            "",
            f"Project: `{request.project}`",
            f"_Decay pass touched {decay_n} row(s)._",
            "",
            "These **active** decisions look important but may be fading from team memory:",
            "",
        ]
        for ec in candidates:
            lines.extend(self._format_candidate(ec))
        lines.extend(
            [
                "",
                "Use slash commands (also repeated under each item on the Feishu card):",
                "- `/decision-review <ec_id> reinforce` — strengthen retention",
                "- `/decision-review <ec_id> expire` — mark expired",
                "- `/decision-review <ec_id> update <new conclusion>` — supersede with new text",
            ]
        )
        return DecisionReviewResult("\n".join(lines), decay_n, candidates)

    def build_review_message(self, request: DecisionReviewRequest) -> str:
        """Backward-compatible: markdown-only string."""
        return self.run_review(request).markdown

    @staticmethod
    def _format_candidate(ec: EventCandidateMetaClass) -> list[str]:
        reasons = "; ".join(ec.reasons) if ec.reasons else "—"
        return [
            f"- `{ec.ec_id}` **{ec.event_name}** (`{ec.status}`)",
            f"  - result: {ec.decision_result[:200]}{'…' if len(ec.decision_result) > 200 else ''}",
            f"  - importance={ec.importance:.2f}, strength={ec.strength:.2f}, reviews={ec.review_count}",
            f"  - reasons: {reasons}",
            "",
        ]
