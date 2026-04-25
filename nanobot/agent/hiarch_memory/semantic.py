from nanobot.agent.hiarch_memory.base import BaseMemoryStore

class SemanticMemoryStore(BaseMemoryStore):
    def __init__(self):
        ...
    
    def retrieve(self, query: str) -> str:
        ...
    
    def update(self, history: str): # update internal storage
        ...