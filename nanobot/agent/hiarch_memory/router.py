from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.utils.helpers import read_jsonlines, write_jsonlines, write_file
from typing import List, Dict, Any
import os
import shutil
from glob import glob

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
        self._windows_size: int = 100; self._overlap: int = 20
        self._episodic = episodic
        self._decision = decision
    
    def operate_batch(self):
        # first step: split `batch` into `slide windows`
        self._create_slide_windows()
        
        # second step: store in episodic & decision memorystore
        for windows_path in glob(os.path.join(self._windows_root, 'window*.jsonl')):
            _window_content: List[Dict[str, Any]] = read_jsonlines(windows_path)
            # 2.1 feedinto episodic
            doc: str = self._episodic.convert_document(_window_content)
            write_file(f'{doc}\n\n', self._document_path, mode='a') # save to .document file
            self._episodic.insert(doc) # insert lightrag
            
            # 2.2 feedinto decision
            

        self._delete_slide_windows()
    
    def _create_slide_windows(self): # .history.jsonl --> windows/window_<idx>.jsonl
        # if os.path.exists(self._windows_root): raise Exception(f'{self._windows_root} could not exist!')
        if os.path.exists(self._windows_root):
            print(f'{self._windows_root} exist! return'); return
        os.makedirs(self._windows_root, exist_ok=False)
        
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
        
