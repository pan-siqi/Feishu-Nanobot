"""Feishu interactive card wrapper for scheduled decision-review digests (Phase 4)."""

from __future__ import annotations

from typing import Any

from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateMetaClass
from nanobot.channels.feishu_card import normalize_interactive_card


def build_decision_review_card(
    markdown_body: str,
    candidates: list[EventCandidateMetaClass],
    *,
    header_title: str = "Decision Review",
) -> dict[str, Any]:
    """
    Schema 2.0 card: summary markdown + per-candidate slash-command hints.

    Native button callbacks require a separate HTTP/card-action subscription; users interact via
    the documented slash commands until that endpoint is wired.
    """
    elements: list[dict[str, Any]] = [{"tag": "markdown", "content": markdown_body.strip()}]
    for ec in candidates[:5]:
        snippet = ec.decision_result[:400] + ("…" if len(ec.decision_result) > 400 else "")
        block = (
            f"### `{ec.ec_id}` · {ec.event_name}\n"
            f"{snippet}\n\n"
            "**Commands**\n"
            f"- `/decision-review {ec.ec_id} reinforce`\n"
            f"- `/decision-review {ec.ec_id} expire`\n"
            f"- `/decision-review {ec.ec_id} update <new conclusion>`\n"
        )
        elements.append({"tag": "markdown", "content": block})
    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "update_multi": True},
        "body": {"elements": elements},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": header_title},
        },
    }
    return normalize_interactive_card(card)
