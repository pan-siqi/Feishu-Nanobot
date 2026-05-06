"""Decision review reminder: decay + stale-important candidate selection (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass

from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore


@dataclass
class DecisionReviewRequest:
    project: str
    limit: int = 3


class DecisionReviewService:
    """Renders a markdown review digest for cron or manual /decision-review."""

    def __init__(self, decision_store: DecisionMemoryStore):
        self._store = decision_store

    def build_review_message(self, request: DecisionReviewRequest) -> str:
        n = self._store.decay()
        candidates = self._store.list_review_candidates(
            project=request.project,
            limit=request.limit,
        )
        if not candidates:
            return ""

        lines = [
            "## Decision Review",
            "",
            f"Project: `{request.project}`",
            f"_Decay pass touched {n} row(s)._",
            "",
            "These **active** decisions look important but may be fading from team memory:",
            "",
        ]
        for ec in candidates:
            lines.extend(self._format_candidate(ec))
        lines.extend(
            [
                "",
                "Reply with one of these commands (when wired):",
                "- `/decision-review <ec_id> reinforce`",
                "- `/decision-review <ec_id> expire`",
                "- `/decision-review <ec_id> update <new statement>`",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_candidate(ec) -> list[str]:
        reasons = "; ".join(ec.reasons) if ec.reasons else "—"
        return [
            f"- `{ec.ec_id}` **{ec.event_name}** ({ec.status})",
            f"  - result: {ec.decision_result[:200]}{'…' if len(ec.decision_result) > 200 else ''}",
            f"  - importance={ec.importance:.2f}, strength={ec.strength:.2f}, reviews={ec.review_count}",
            f"  - reasons: {reasons}",
            "",
        ]
