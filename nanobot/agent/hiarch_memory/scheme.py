from enum import Enum

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal
import os

TOPICS = ['inter_mediate', 'event_candidate']


def load_description(topic_idx: int, key_name: str) -> str:
    cwd = os.path.dirname(os.path.abspath(__file__))
    real_path: str = os.path.join(cwd, f'description/{TOPICS[topic_idx]}/{key_name}.md')
    with open(real_path, mode='r', encoding='utf-8') as reader:
        content = reader.read()
    return content.strip()


class DecisionStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class InterMediate(BaseModel):
    type: Literal['fact', 'preference', 'goal', 'task', 'constraint', 'relationship']
    topic: str = Field(..., description=load_description(0, 'topic'))
    importance: float = Field(..., ge=0.0, le=1.0, description=load_description(0, 'importance'))
    ttl_days: int = Field(..., ge=1, le=3650, description=load_description(0, 'ttl_days'))
    content: str = Field(..., min_length=1, description=load_description(0, 'content'))

class InterMediateResult(BaseModel):
    result: List[InterMediate]

class EventCandidate(BaseModel):
    event_name: str = Field(..., min_length=1, description=load_description(1, 'event_name'))
    decision_signal: Literal['decided', 'agreed', 'rejected', 'changed', 'postponed', 'cancelled', 'tentative', 'open_question'] = Field(..., description=load_description(1, 'decision_signal'))
    summary: str = Field(..., min_length=1, description=load_description(1, 'summary'))
    decision_result: str = Field(..., min_length=1, description=load_description(1, 'decision_result'))
    aliases: List[str] = Field(default_factory=list, description="事件别名或简称，可空")
    entities: List[str] = Field(default_factory=list, description=load_description(1, 'entities'))
    evidence_message_ids: List[str] = Field(..., min_length=1, description=load_description(1, 'evidence_message_ids'))
    confidence: float = Field(..., ge=0.0, le=1.0, description=load_description(1, 'confidence'))
    reasons: List[str] = Field(default_factory=list, description="支持该结论的理由要点")
    objections: List[str] = Field(default_factory=list, description="讨论中出现的反对意见或风险")
    alternatives: List[str] = Field(default_factory=list, description="被否决或未被采纳的备选方案")
    deadline: str | None = Field(default=None, description="时间约束或截止日（原文摘录，无则 null）")
    participants: List[str] = Field(default_factory=list, description="参与决策的人员姓名或标识")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="对团队后续协作的重要程度，独立于 confidence")

class EventCandidateResult(BaseModel):
    result: List[EventCandidate]

class EventCandidateMergeResult(BaseModel):
    ec_id: str = Field(..., description='即将被合并的事件的ec_id')
    event_candidate: EventCandidate = Field(..., description='合并后的事件结果')
