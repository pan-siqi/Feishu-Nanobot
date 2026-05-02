import jsonlines
from typing import List, Dict, Any

def find_legal_message_start(messages: list[dict[str, Any]]) -> int:
    declared: set[str] = set()
    start = 0
    for i, msg in enumerate(messages):
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    declared.add(str(tc["id"]))
        elif role == "tool":
            tid = msg.get("tool_call_id")
            if tid and str(tid) not in declared:
                start = i + 1
                declared.clear()
                for prev in messages[start : i + 1]:
                    if prev.get("role") == "assistant":
                        for tc in prev.get("tool_calls") or []:
                            if isinstance(tc, dict) and tc.get("id"):
                                declared.add(str(tc["id"]))
    return start

class Session:
    def __init__(self, session_dir: str):
        self._session_dir = session_dir
        self._session = self._load_session()
        self.key = 'custom'
    
    def get_history(self, max_messages: int = 500, clip_index: int = 0) -> list[dict[str, Any]]:
        message_clipped = self._session[clip_index:]
        sliced = message_clipped[-max_messages:]

        # Avoid starting mid-turn when possible.
        for i, message in enumerate(sliced):
            if message.get("role") == "user":
                sliced = sliced[i:]
                break

        # Drop orphan tool results at the front.
        start = find_legal_message_start(sliced)
        if start:
            sliced = sliced[start:]

        out: list[dict[str, Any]] = []
        for message in sliced:
            entry: dict[str, Any] = {"role": message["role"], "content": message.get("content", "")}
            for key in ("tool_calls", "tool_call_id", "name", "reasoning_content"):
                if key in message:
                    entry[key] = message[key]
            out.append(entry)
        return out
    
    def _load_session(self) -> List[Dict]:
        session: List[Dict] = list()
        with jsonlines.open(self._session_dir, mode='r') as reader:
            for obj in reader:
                session.append(obj)
        return session