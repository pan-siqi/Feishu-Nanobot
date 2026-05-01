"""Decision review reminder helpers."""

from __future__ import annotations

from dataclasses import dataclass

from nanobot.agent.hiarch_memory.decision import Decision, DecisionMemoryStore


@dataclass
class DecisionReviewRequest:
    project: str
    limit: int = 3


class DecisionReviewService:
    """Select stale-important decisions and render a review message."""

    def __init__(self, decision_store: DecisionMemoryStore):
        self._store = decision_store

    def build_review_message(self, request: DecisionReviewRequest) -> str:
        # Update strength decay before selecting today's review candidates.
        self._store.decay()
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
            "",
            "These decisions look important but stale. Please review:",
            "",
        ]
        for d in candidates:
            lines.extend(self._format_candidate(d))
        lines.extend(
            [
                "",
                "Reply with one of these commands:",
                "- `/decision-review <id> reinforce`",
                "- `/decision-review <id> expire`",
                "- `/decision-review <id> update <new statement>`",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_candidate(d: Decision) -> list[str]:
        reasons = "; ".join(d.reasons) if d.reasons else "—"
        return [
            f"- `{d.id}` **{d.topic}**: {d.statement}",
            f"  - importance={d.importance:.2f}, strength={d.strength:.2f}, reviews={d.review_count}",
            f"  - reasons: {reasons}",
        ]
