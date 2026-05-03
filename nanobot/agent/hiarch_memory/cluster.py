from nanobot.agent.hiarch_memory.scheme import EventCandidate, EventCandidateResult
from nanobot.utils.helpers import read_jsonlines, write_jsonlines
from typing import List, Dict
import os

class Cluster:
    def __init__(
            self,
            workspace: str,
            mem_save_path: str,
        ):
        self._workspace = workspace; self._mem_save_path = mem_save_path
        self._cluster_save_path = os.path.join(self._mem_save_path, '.cluster.jsonl')
        self._init_cluster_path()
    
    def push(self, ec: EventCandidate):
        _cluster_content: List[Dict] = read_jsonlines(self._cluster_save_path)
        if not _cluster_content: # no content
            ...
    
    def _init_cluster_path(self):
        with open(self._cluster_save_path, mode='w', encoding='utf-8') as writer:
            writer.write('')