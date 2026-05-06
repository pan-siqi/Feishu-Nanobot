from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.utils.helpers import read_jsonlines, write_jsonlines, write_file, write_pickle, read_pickle
from typing import List, Dict, Any
import os
import shutil
from glob import glob
from uuid import uuid4

class Router:
    def __init__(
        self,
        mem_save_path: str,
        history_save_path: str,
        episodic: EpisodicMemoryStore,
        decision: DecisionMemoryStore,
    ):
        self._mem_save_path = mem_save_path; self._history_save_path = history_save_path
        self._windows_root = os.path.join(self._mem_save_path, '.windows')
        self._document_path = os.path.join(self._mem_save_path, '.document.txt')
        self._windows_recorded_path = os.path.join(self._windows_root, '.record.pkl')
        self._evidence_message_ids_path = os.path.join(self._mem_save_path, '.evids.pkl')
        self._windows_size: int = 100; self._overlap: int = 20
        self._episodic = episodic
        self._decision = decision
    
    async def operate_batch(self):
        # first step: split `batch` into `slide windows`
        self._create_slide_windows()
        
        # second step: store in episodic & decision memorystore
        for windows_path in glob(os.path.join(self._windows_root, 'window*.jsonl')):
            if windows_path in self._windows_recorded: continue
            _window_content: List[Dict[str, Any]] = read_jsonlines(windows_path)
            # 2.1 feedinto episodic
            doc: str = await self._episodic.convert_document(_window_content)
            # write_file(f'{doc}\n\n', self._document_path, mode='a') # save to .document file
            await self._episodic.insert(doc) # insert lightrag
            
            # 2.2 feedinto decision
            self._add_extra_message_id(_window_content) # add message id
            _evidence_message_ids = await self._decision.extract(_window_content) # extract event candidate, insert database
            self._merge_evidence_message_ids(_evidence_message_ids)
            self._windows_recorded.append(windows_path)
            write_pickle(self._windows_recorded, self._windows_recorded_path)

        self._delete_slide_windows()
    
    def _create_slide_windows(self): # .history.jsonl --> windows/window_<idx>.jsonl
        # if os.path.exists(self._windows_root): raise Exception(f'{self._windows_root} could not exist!')
        if os.path.exists(self._windows_root):
            self._windows_recorded: List = read_pickle(self._windows_recorded_path)
            print(f'{self._windows_root} exist! return'); return
        
        os.makedirs(self._windows_root, exist_ok=False)
        self._windows_recorded: List = list()
        write_pickle(self._windows_recorded, self._windows_recorded_path)

        _temp: List[Dict] = read_jsonlines(self._history_save_path)
        left: int = 0
        while True:
            right: int = min(left+self._windows_size, len(_temp)-1) # update right idx
            _windows_path: str = os.path.join(self._windows_root, f'window{left+1}_{right}.jsonl')
            write_jsonlines(_temp[left: right], _windows_path)
            left = right - self._overlap # update left idx
            if len(_temp) - 1 - right == 0: break # full walk
    
    def _delete_slide_windows(self):
        shutil.rmtree(self._windows_root) # remove windows root dir
        self._windows_recorded: List = list()
        
    def _add_extra_message_id(self, _window_content: List[Dict[str, Any]]):
        self._windows_message_ids: List[str] = list()
        for win in _window_content:
            message_id: str = f'm{uuid4().hex[:10]}'
            win['message_id'] = message_id
            self._windows_message_ids.append(message_id)
    
    def _merge_evidence_message_ids(self, evidence_message_ids: List[str]):
        # filter not exists in _windows_message_ids
        _evidence_message_ids: List = [emi for emi in evidence_message_ids if emi not in self._windows_message_ids]
        _evidence_message_ids_history: List[str] = read_pickle(self._evidence_message_ids_path) if os.path.exists(self._evidence_message_ids_path) else list()

        # merge
        for evid in _evidence_message_ids:
            if evid not in _evidence_message_ids_history:
                _evidence_message_ids_history.append(evid)
        
        # save
        write_pickle(_evidence_message_ids_history, self._evidence_message_ids_path)