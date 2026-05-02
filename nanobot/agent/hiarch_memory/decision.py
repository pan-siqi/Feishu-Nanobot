from nanobot.agent.hiarch_memory.base import BaseMemoryStore
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class EventCandidate(BaseModel):
    event_name: str
    decision_signal: str
    summary: str
    decision_result: str
    entities: List[str]
    evidence_message_ids: List[str]
    confidence: float

class EventCandidateResult(BaseModel):
    result: List[EventCandidate]


class DecisionMemoryStore(BaseMemoryStore):
    def __init__(self):
        ...
    
    def extract(self, history: List[Dict[str, Any]]) -> str:
        # extract event candidates
        ...
    
    def update(self, history: str): # update internal storage
        ...