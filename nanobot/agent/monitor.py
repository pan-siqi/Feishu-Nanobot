from nanobot.agent.hiarch_memory.database.ec_database import Session as DataBaseSession
from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateRepository, EventCandidateMetaClass
from nanobot.utils.prompt_templates import render_template
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.session.manager import Session, SessionManager
from nanobot.channels.feishu_card import resolve_interactive_card
from typing import List, Dict, Tuple
import json

class Monitor:
    def __init__(
            self,
            bus: MessageBus,
            database_session: DataBaseSession,
            repo: EventCandidateRepository,
        ):
        self.bus = bus
        self._signal: bool = False
        self._session = database_session
        self._repo = repo

    async def check(self, session: Session, msg: InboundMessage) -> bool:
        if not await self._block_message(session):
            self._signal = True
        
        await self._publish_card(session, msg)
        
        if self._signal:
            return True
        return False
    
    async def _block_message(self, session: Session) -> bool:
            """
            Return True when the current non-mentioned group message should be read
            without replying. The gate only sees a small recent window to avoid
            growing token cost with the full session history.
            当当前未提及的群组消息应被阅读而不需回复时，返回 True。
            该闸门仅查看最近的一小段历史记录，以避免因包含完整会话历史记录而导致令牌消耗增加。
            """
            # recent_user_messages = [
            #     message
            #     for message in session.messages[-20:]
            #     if message.get("role") == "user" and isinstance(message.get("content"), str)
            # ]
            # recent_context = "\n".join(
            #     f"- {message.get('timestamp', '')} {message['content']}"
            #     for message in recent_user_messages[-12:]
            # )
            # prompt = render_template(
            #     "custom/group_reply_gate.md",
            #     strip=True,
            #     value=recent_context,
            # )
            # messages = [{"role": "user", "content": prompt}]
            # response = self.provider.chat_with_retry(messages)
            # decision_text = ""
            # if isinstance(response, str):
            #     decision_text = response
            # elif isinstance(response, dict):
            #     decision_text = str(response.get("content", ""))
            # else:
            #     decision_text = str(response)
            # decision = decision_text.strip().lower()
            # current_content = session.messages[-1].get("content", "") if session.messages else ""
            # should_reply = decision in {"reply", "true", "yes", "需要回复", "回复"}
            # logger.info("Reply gate for {}: decision={}, message={}", session.key, decision, current_content)
            
            # return not should_reply
            return False

    async def _publish_card(self, session: Session, msg: InboundMessage) -> bool:
        '''
        如果觉得这个session应该推送了, 就推送卡片
        '''
        # first step: search from database
        # if True:
        #     return False

        # second step: search from database
        meta = dict(msg.metadata or {})
        result: List[Tuple[EventCandidateMetaClass, float]] = self._repo.retrieve(msg.content)

        test_json_path: str = '/root/workspace/Feishu-Nanobot/nanobot/agent/hiarch_memory/test.json'
        with open(test_json_path, mode='r', encoding='utf-8') as reader:
            card_content = json.loads(reader.read())

        # card_content: str = '\n\n'.join([self.convert_ec_to_beautify_markdown(ec) for ec, score in result])
        # meta['_card_json'] = resolve_interactive_card(meta, default_markdown=card_content, default_header_title='Nanobot')
        meta['_card_json'] = card_content

        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=card_content,
                metadata=meta,
            )
        )
        return True


    def convert_ec_to_beautify_markdown(self, ec: EventCandidateMetaClass) -> str:
         return render_template('custom/beaucanonical.md', strip=True, 
                         event_name=ec.event_name, aliases=', '.join(ec.aliases), decision_signal=ec.decision_signal,
                         summary=ec.summary, decision_result=ec.decision_result, entities=', '.join(ec.entities))