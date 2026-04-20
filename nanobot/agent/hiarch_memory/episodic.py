from typing import List, Dict, Any, Literal, cast
import jsonlines
import os
from pydantic import BaseModel, Field
from nanobot.utils.prompt_templates import render_template
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.providers.base import LLMResponse, LLMResponseStructure
import json
from uuid import uuid4
import time
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import volcengine_openai_complete, LocalModelEmbed, openai_embed
from lightrag.utils import setup_logger, EmbeddingFunc


class InterMediate(BaseModel):
    type: Literal["fact", "preference", "goal", "task", "constraint", "relationship"]
    topic: str = Field(..., description="Short normalized topic name, snake_case preferred")
    importance: float = Field(..., ge=0.0, le=1.0, description="0=trivial, 0.5=useful, 1=critical long-term memory")
    ttl_days: int = Field(..., ge=1, le=3650, description="How long this memory remains relevant (in days)")
    content: str = Field(..., min_length=1, description="Concise factual statement, no fluff")


class InterMediateResult(BaseModel):
    result: List[InterMediate]


class EpisodicMemoryStore:
    def __init__(self, workspace: str, provider: OpenAICompatProvider, model: str):
        self._workspace = workspace; self._provider = provider; self._model = model
        self._mem_save_path = os.path.join(self._workspace, 'memory')
        self._save_path = os.path.join(self._mem_save_path, '.history.jsonl')
        self._scheme_path = './nanobot/nanobot/agent/hiarch_memory/itermediate.json'
        self._embed_model_path = './model/bge-small-zh-v1.5/'
        self._document_save_path = os.path.join(self._mem_save_path, '.document.md')
        self._lightrag_workspace = os.path.join(self._mem_save_path, 'rag_storage')
        self._initial_lightrag: bool = False

    async def initial_lightrag(self): # MUST CALL!
        embed_model = LocalModelEmbed(self._embed_model_path)
        embed_func = EmbeddingFunc(embed_model.embedding_dim, embed_model.embed, embed_model.max_token_size)
        self._rag = LightRAG(
            working_dir=self._lightrag_workspace,
            embedding_func=embed_func,
            llm_model_func=volcengine_openai_complete,
            graph_storage="Neo4JStorage",
        )
        await self._rag.initialize_storages()

    async def retrieve(self, query: str) -> str:
        if not hasattr(self, '_rag'): return ''
        result: str = await self._rag.aquery(query, param=QueryParam(mode="hybrid"))
        return result

    async def check(self):
        if not self._initial_lightrag: await self.initial_lightrag()
        await self._jsonline_to_document()

    def can_retrieve(self) -> bool:
        return os.path.exists(self._lightrag_workspace)

    async def _jsonline_to_document(self, clean_doc: bool=True, clean_history: bool=True):
        history: List[Dict[str, Any]] = self._load_history()
        histext: str = self._format_messages(history)
        msg: List[Dict[str, Any]] = [
            {'role': 'system', 'content': render_template('custom/extract.md', strip=True)},
            {'role': 'user', 'content': histext},
        ]
        _scheme = InterMediateResult
        # _scheme = self._load_scheme()
        memunit = None
        self._provider.set_scheme(_scheme)
        response = await self._provider.chat_scheme(msg, model=self._model, tools=None, tool_choice=None)
        if isinstance(response, LLMResponse):
            raise Exception('fail to build scheme')
        if response.parsed: memunit: str = self._intermediate_to_document(response.parsed)
        if memunit: await self._rag.ainsert(memunit)
        # if clean_doc: self._cleanup_document()
        # if clean_history: self._cleanup_history()
    
    def _intermediate_to_document(self, imeres: Dict) -> str:
        memunit: str = ''
        for ime in imeres.get('result'):
            ime = cast(dict, ime)
            memunit += render_template('custom/memunit.md', strip=True, 
                                       uid=uuid4().hex[:5], type=ime.get('type'), topic=ime.get('topic'), importance=ime.get('importance'),
                                       ttl_days=ime.get('ttl_days'), ts=int(time.time()), content=ime.get('content')).strip()
            memunit += '\n\n'
        self._write_document(f'{memunit}')
        return memunit
    
    def _cleanup_history(self):
        os.remove(self._save_path)

    def _load_history(self) -> List[Dict[str, Any]]:
        _records = []
        with jsonlines.open(self._save_path, mode='r') as reader:
            for obj in reader:
                _records.append(obj)
        return _records
    
    def _load_scheme(self) -> Dict:
        with open(self._scheme_path, mode='r', encoding='utf-8') as reader:
            content = json.loads(str(reader.read().strip()))
        return content
    
    def _cleanup_document(self):
        os.remove(self._document_save_path) # remove file

    def _write_document(self, ctn: str):
        with open(self._document_save_path, mode='w', encoding='utf-8') as writer:
            writer.write(ctn)

    def _format_messages(self, messages: List[Dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)