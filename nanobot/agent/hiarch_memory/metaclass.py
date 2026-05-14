from dataclasses import dataclass

@dataclass
class FileName:
    history: str       = '.history.jsonl'
    cursor: str        = '.cursor'
    shortermem: str    = '.shortermem.jsonl'
    windows_root: str   = '.windows'
    windows_record: str = '.record.pkl'
    evidence: str      = '.evids.pkl'
    document: str      = '.document.txt'
    rag_workspace: str = 'rag_storage'
    logger: str        = '.log'

