import os
from typing import List, Tuple

from nanobot.agent.hiarch_memory.database.ec_database import Session as DataBaseSession
from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateMetaClass, EventCandidateRepository
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.feishu_card import resolve_interactive_card
from nanobot.session.manager import Session
from nanobot.utils.prompt_templates import render_template
from loguru import logger

_DEFAULT_CARD_MAX_DISTANCE = float(os.environ.get("NANOBOT_MONITOR_CARD_MAX_DISTANCE", "0.35"))


class Monitor:
    """
    Optional read-only gate + proactive decision cards.
    Card push only when vector retrieval returns hits within distance threshold.
    """

    def __init__(
        self,
        bus: MessageBus,
        database_session: DataBaseSession,
        repo: EventCandidateRepository,
        *,
        card_max_distance: float | None = None,
    ):
        self.bus = bus
        self._session = database_session
        self._repo = repo
        self._card_max_distance = (
            float(card_max_distance)
            if card_max_distance is not None
            else _DEFAULT_CARD_MAX_DISTANCE
        )

    async def check(self, session: Session, msg: InboundMessage) -> bool:
        """Return True to skip the agent loop for this message ('read but no reply')."""
        read_only = await self._block_message(session)
        await self._publish_card(session, msg)
        return read_only

    async def _block_message(self, session: Session) -> bool:
        """
        Return True when the message should be consumed without an LLM reply.
        Reserved for group_reply_gate.md style logic; currently never suppresses.
        """
        _ = session
        return False

    async def _publish_card(self, session: Session, msg: InboundMessage) -> bool:
        _ = session
        text = (msg.content or "").strip()
        if not text:
            logger.debug("Monitor card: skip (empty inbound text)")
            return False

        result: List[Tuple[EventCandidateMetaClass, float]] = self._repo.retrieve(text)
        if not result:
            logger.info("Monitor card: skip (no EventCandidate within repo filter)")
            return False

        best_score = result[0][1]
        if best_score >= self._card_max_distance:
            logger.info(
                "Monitor card: skip (best_distance={:.4f} >= threshold={:.4f})",
                best_score,
                self._card_max_distance,
            )
            return False

        card_md = "\n\n".join(self.convert_ec_to_beautify_markdown(ec) for ec, _ in result)
        meta = dict(msg.metadata or {})
        meta["_card_json"] = resolve_interactive_card(
            meta,
            default_markdown=card_md,
            default_header_title="Nanobot",
        )

        outbound_text = card_md if len(card_md) <= 2000 else card_md[:1997] + "..."
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=outbound_text,
                metadata=meta,
            )
        )
        logger.info(
            "Monitor card: pushed hits={} best_distance={:.4f} channel={} chat_id={}",
            len(result),
            best_score,
            msg.channel,
            msg.chat_id,
        )
        return True

    def convert_ec_to_beautify_markdown(self, ec: EventCandidateMetaClass) -> str:
        return render_template(
            "custom/beaucanonical.md",
            strip=True,
            event_name=ec.event_name,
            aliases=", ".join(ec.aliases),
            decision_signal=ec.decision_signal,
            summary=ec.summary,
            decision_result=ec.decision_result,
            entities=", ".join(ec.entities),
        )
