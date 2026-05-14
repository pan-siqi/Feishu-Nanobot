from nanobot.agent.hiarch_memory.episodic import EpisodicMemoryStore
from nanobot.agent.hiarch_memory.decision import DecisionMemoryStore
from nanobot.agent.hiarch_memory.metaclass import FileName
from nanobot.utils.helpers import read_jsonlines, write_jsonlines, write_file, write_pickle, read_pickle
from nanobot.session.manager import Session
from typing import List, Dict, Any, Callable
import os
import shutil
from glob import glob
from uuid import uuid4
from loguru import logger
from datetime import datetime

class Router:
    def __init__(
        self,
        mem_save_path: str,
        episodic: EpisodicMemoryStore,
        decision: DecisionMemoryStore,
    ):
        self._mem_save_path = mem_save_path
        self._windows_size: int = 100
        self._overlap: int = 20
        self._episodic = episodic
        self._decision = decision
    
    async def operate_batch(self, session: Session, project_id: str):
        _project_path: str = os.path.join(self._mem_save_path, project_id)
        if not os.path.exists(_project_path): os.mkdir(_project_path)
        
        _windows_root        = os.path.join(_project_path, FileName.windows_root)
        _history_path        = os.path.join(_project_path, FileName.history)
        _windows_record_path = os.path.join(_project_path, FileName.windows_root, FileName.windows_record)
        _evidence_path       = os.path.join(_project_path, FileName.evidence)
        _logger_path         = os.path.join(_project_path, FileName.logger)
        # add logger path
        logger.remove(); logger.add(_logger_path)
        logger.info(f'Start to Operate Batch...')

        # first step: split `batch` into `slide windows`
        self._create_slide_windows(_windows_root, _history_path, _windows_record_path)

        # second step: store in episodic & decision memorystore
        processed = 0
        windows_path_list: List[str] = glob(os.path.join(_windows_root, 'window*.jsonl'))
        logger.info(f'Split {len(windows_path_list)} windows')

        for idx, windows_path in enumerate(windows_path_list):
            logger.info(f'Now operate {idx}-th window content.')
            if windows_path in self._windows_record:
                logger.info(f'current window have operated')
                continue 
            
            _windows_content: List[Dict[str, Any]] = read_jsonlines(windows_path)
            _windows_content_string: str = ''
            for wc_idx, wc in enumerate(_windows_content):
                _windows_content_string += '[{}]{}: {}\n'.format(wc_idx, wc['role'], wc['content'][0: 100])
            logger.info(f'current window content: \n{_windows_content_string}')
            
            # 2.1 feedinto episodic
            doc: str = await self._episodic.convert_document(_windows_content)
            # write_file(f'{doc}\n\n', self._document_path, mode='a') # save to .document file
            await self._episodic.insert(doc, project_id) # insert lightrag
            
            # 2.2 feedinto decision
            self._add_extra_message_id(_windows_content) # add message id
            _evidence_message_ids = await self._decision.extract(_windows_content, project_id)
            self._merge_evidence_message_ids(_evidence_message_ids, _evidence_path, _windows_content)
            
            # 2.3 record windows_path
            self._windows_record.append(windows_path)
            write_pickle(self._windows_record, _windows_record_path)
            processed += 1
        
        # final step: delete slide windows
        self._delete_slide_windows(_windows_root)
    
    def _create_slide_windows(self, _windows_root: str, _history_path: str, _windows_record_path: str): # .history.jsonl --> windows/window_<idx>.jsonl
        # if os.path.exists(self._windows_root): raise Exception(f'{self._windows_root} could not exist!')
        
        if os.path.exists(_windows_root):
            self._windows_record: List = read_pickle(_windows_record_path)
            logger.warning(f'{_windows_root} exist! return '); return 
        
        os.makedirs(_windows_root, exist_ok=False)
        self._windows_record: List = list()
        write_pickle(self._windows_record, _windows_record_path)

        _temp: List[Dict] = read_jsonlines(_history_path)
        # _temp = session.messages
        left: int = 0
        while True:
            right: int = min(left+self._windows_size, len(_temp)-1) # update right idx
            _windows_path: str = os.path.join(_windows_root, f'window{left+1}_{right}.jsonl')
            write_jsonlines(_temp[left: right], _windows_path)
            left = right - self._overlap # update left idx
            if len(_temp) - 1 - right == 0: break # full walk
    
    def _delete_slide_windows(self, _windows_root: str):
        shutil.rmtree(_windows_root) # remove windows root dir
        self._windows_record: List = list()
        
    def _add_extra_message_id(self, _windows_content: List[Dict[str, Any]]):
        for win in _windows_content:
            message_id: str = f'm{uuid4().hex[:10]}'
            win['message_id'] = message_id
    
    def _merge_evidence_message_ids(
            self,
            evidence_message_ids: List[str],
            evidence_path: str,
            _windows_content: List[Dict[str, Any]],
        ):
        # exists message id list
        _windows_content_message_ids: List[str] = [win.get('message_id') for win in _windows_content]
        
        # filter not exists in _windows_content_message_ids
        _evidence_message_ids: List = [emi for emi in evidence_message_ids if emi in _windows_content_message_ids]
        _evidence_message_ids_history: List[str] = read_pickle(evidence_path) if os.path.exists(evidence_path) else list()
        
        # merge
        for evid in _evidence_message_ids:
            if evid not in _evidence_message_ids_history:
                _evidence_message_ids_history.append(evid)
        
        # save
        write_pickle(_evidence_message_ids_history, evidence_path)