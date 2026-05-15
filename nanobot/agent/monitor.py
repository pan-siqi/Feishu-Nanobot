from nanobot.agent.hiarch_memory.database import DataBaseSession, EventCandidateMetaClass, EventCandidateRepository
from nanobot.agent.card import build_card
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.feishu_card import resolve_interactive_card
from nanobot.session.manager import Session
from nanobot.utils.prompt_templates import render_template
from loguru import logger
from typing import List, Tuple
from datetime import datetime
import os

_DEFAULT_CARD_MAX_DISTANCE = 0.35

class Monitor:
    def __init__(
        self,
        bus: MessageBus,
        database_session: DataBaseSession,
        repo: EventCandidateRepository,
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

    async def check(
            self,
            project_id: str,
            session: Session,
            msg: InboundMessage,
            initial_messages: list[dict],
        ) -> Tuple[bool, list[dict]]:
        messages = initial_messages
        read_only = await self._block_message(session, msg)
        publish_result = await self._publish_card(project_id, session, msg)
        if not publish_result: return read_only, messages, None
        
        # update publish result
        card_message, card_outboundmessage = publish_result
        messages.append(card_message)
        return read_only, messages, card_outboundmessage

    async def _block_message(self, session: Session, msg: InboundMessage) -> bool:
        if msg.is_mentioned:
            return False
        return True

    async def _publish_card(self, project_id: str, session: Session, msg: InboundMessage) -> None | Tuple[dict, OutboundMessage]:
        if not msg.is_mentioned: return

        text = (msg.content or "").strip()
        result: List[Tuple[EventCandidateMetaClass, float]] = self._repo.retrieve(text, project_id)
        if not result: return
        
        card_json, card_md = build_card([self.convert_ec_to_beautify_markdown(ec) for ec, _ in result])
        meta = dict(msg.metadata or {})
        meta["_card_json"] = card_json

        outbound_text = card_md if len(card_md) <= 2000 else card_md[:1997] + "..."
        card_message = {'role': 'assistant', 'content': outbound_text, 'timestamp': datetime.now().isoformat()}
        card_outboundmessage = \
        OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=outbound_text,
            metadata=meta,
        )
        return card_message, card_outboundmessage
        

    def convert_ec_to_beautify_markdown(self, ec: EventCandidateMetaClass) -> str:
        return render_template(
            "custom/beaucanonical.md",
            strip          = True,
            event_name     = ec.event_name,
            project_id     = ec.project_id,
            importance     = ec.importance,
            status         = ec.status,
            strength       = ec.strength,
            aliases        = ", ".join(ec.aliases),
            decision_signal= ec.decision_signal,
            summary        = ec.summary,
            decision_result= ec.decision_result,
            entities       = ", ".join(ec.entities),
        )
