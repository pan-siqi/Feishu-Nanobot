from typing import List, Dict, Tuple, Optional, Any, cast
import os
import jsonlines
from uuid import uuid4
import datetime
import faiss
from sentence_transformers import SentenceTransformer
import numpy as np
from numpy import ndarray
'''
Indentify --> Extract --> Graph --> Save --> Retrieve --> Activate
'''

class EpisodicMemoryStore:
    def __init__(self, workspace: str):
        self._workspace = workspace
        self._mem_save_path = os.path.join(self._workspace, 'memory')
        if not os.path.exists(self._mem_save_path):
            os.mkdir(self._mem_save_path)
        self._save_path = os.path.join(self._mem_save_path, 'over_history.jsonl')
        self._document_save_path = os.path.join(self._mem_save_path, 'document.jsonl')
        self._index_save_path = os.path.join(self._mem_save_path, 'index.faiss')
        self._index: Optional[faiss.IndexFlatIP] = self._load_index() if os.path.exists(self._index_save_path) else None
        _model_path: str = '/home/deepmiemie/Proj/Openclaw/models/beg-small-zh-v1.5'
        self._embedding_model = SentenceTransformer(_model_path)
        self._batch_size: int = 32
        self._top_k: int = 3
    
    def check(self) -> bool: # build vector database
        res, docs = self._jsonlines_to_document()
        if res:
            self._document_to_vectordatabase(docs)
        return True

    def retrieve(self, query: str) -> Optional[List[Dict]]: # retrieve based on query
        if not self.can_retrieve():
            return 
        query_vec = self._embedding_model.encode([query], normalize_embeddings=True)
        scores, indices = self._index.search(query_vec, self._top_k)
        scores, indices = cast(ndarray, scores), cast(ndarray, indices)
        scores, indices = scores.tolist(), indices.tolist()
        _docs = self._load_document()
        results = []
        for score, idx in zip(scores[0], indices[0]):
            doc = _docs[idx]
            results.append({'score': float(score), 'source': doc})
        return results
    
    def can_retrieve(self) -> bool:
        metric = os.path.exists(self._index_save_path)
        return metric

    def _document_to_vectordatabase(self, docs: List[Dict[str, Any]]) -> bool:
        texts = [d.get('text') for d in docs]
        embeddings = self._embedding_model.encode(texts, batch_size=self._batch_size, normalize_embeddings=True)
        dim: int = embeddings.shape[1]
        if self._index is None: self._index = faiss.IndexFlatIP(dim) # firse build _index
        self._index.add(embeddings)
        self._save_index() # write to diss
        return True

    def _jsonlines_to_document(self) -> Tuple[bool, Optional[List]]: # currently only consider `user` & `assistant`
        history = self._load_history()
        if not history:
            return False, None
        _temp: List = []
        _temp_text: List = []
        while history:
            ctn = history.pop(0)
            if ctn.get('role') == 'user':
                if _temp: _temp_text.append({'time': self._get_datetime(), 'text': self._transfer_text(_temp)})
                _temp = [] # cleanup _temp
            _temp.append(ctn)
        # if _temp not empty, then also push
        if _temp: _temp_text.append({'time': self._get_datetime(), 'text': self._transfer_text(_temp)})
        
        self._save_document(_temp_text) # write to diss
        return True, _temp_text
    
    def _transfer_text(self, temp: List[Dict[str, Any]]) -> str:
        result: str = ''
        for idx, t in enumerate(temp):
            if idx != 0: result += '\n'
            result += '{}: {}'.format(t.get('role'), str(t.get('content')))
        return result
    
    def _save_document(self, docs: List[Dict]):
        with jsonlines.open(self._document_save_path, mode='w') as writer:
            writer.write_all(docs)
        
    def _load_document(self) -> List[Dict[str, Any]]:
        contents = []
        with jsonlines.open(self._document_save_path, mode='r') as reader:
            for obj in reader:
                contents.append(obj)
        return contents

    def _save_index(self):
        faiss.write_index(self._index, self._index_save_path)
    
    def _load_index(self) -> faiss.IndexFlatIP:
        return faiss.read_index(self._index_save_path)

    def _load_history(self) -> List[Dict[str, Any]]:
        _records = []
        with jsonlines.open(self._save_path, mode='r') as reader:
            for obj in reader:
                _records.append(obj)
        return _records
    
    def _clear_history(self):
        with open(self._save_path, mode='w') as writer:
            writer.write('')

    def _get_datetime(self) -> str:
        return datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')