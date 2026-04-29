"""Structured decision memory: extract (LLM + schema), store (SQLite + optional LightRAG)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Literal, cast

from loguru import logger
from pydantic import BaseModel, Field

from nanobot.providers.base import LLMResponse, LLMResponseStructure
from nanobot.providers.openai_compat_provider import OpenAICompatProvider
from nanobot.utils.helpers import ensure_dir
from nanobot.utils.prompt_templates import render_template


class DecisionExtractItem(BaseModel):
    """Single row returned by the extraction LLM (Sprint 1 schema)."""

    topic: str = Field(..., description="Normalized topic, snake_case preferred")
    statement: str = Field(..., description="One-sentence conclusion")
    reasons: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    decided_at: int | None = Field(
        default=None,
        description="Unix timestamp when the decision was made; omit for 'now'",
    )
    deadline: int | None = Field(default=None, description="Unix deadline or null")
    participants: list[str] = Field(default_factory=list, description="Participant ids or display names")
    source: Literal["chat", "doc", "cli", "manual"] = "chat"
    source_ref: str = Field(default="unknown", description="message_id / doc_token / etc.")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class DecisionExtractResult(BaseModel):
    result: list[DecisionExtractItem] = Field(default_factory=list)


class Decision(BaseModel):
    """Full persisted decision (aligns with proposal `decisions` table)."""

    id: str
    project: str
    topic: str
    statement: str
    reasons: list[str]
    objections: list[str]
    alternatives: list[str]
    decided_at: int
    deadline: int | None
    participants: list[str]
    source: Literal["chat", "doc", "cli", "manual"]
    source_ref: str
    importance: float
    last_reviewed_at: int
    review_count: int = 0
    strength: float = 1.0
    supersedes: str | None = None
    status: Literal["active", "superseded", "expired"] = "active"

    def reasons_json(self) -> str:
        return json.dumps(self.reasons, ensure_ascii=False)

    def objections_json(self) -> str:
        return json.dumps(self.objections, ensure_ascii=False)

    def alternatives_json(self) -> str:
        return json.dumps(self.alternatives, ensure_ascii=False)

    def participants_json(self) -> str:
        return json.dumps(self.participants, ensure_ascii=False)


class DecisionMemoryStore:
    """SQLite-backed decision store with optional dual-write to Episodic LightRAG."""

    _IMPORTANCE_FLOOR = 0.3

    def __init__(
        self,
        workspace: str | Path,
        provider: OpenAICompatProvider,
        model: str,
        episodic: Any | None = None,
    ):
        self._workspace = Path(workspace)
        self._provider = provider
        self._model = model
        self._episodic = episodic
        self._mem_dir = ensure_dir(self._workspace / "memory")
        self._db_path = self._mem_dir / "decisions.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    project TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    objections TEXT NOT NULL,
                    alternatives TEXT NOT NULL,
                    decided_at INTEGER NOT NULL,
                    deadline INTEGER,
                    participants TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    last_reviewed_at INTEGER NOT NULL,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    strength REAL NOT NULL DEFAULT 1.0,
                    supersedes TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_project_topic ON decisions(project, topic)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status_importance ON decisions(status, importance)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_last_reviewed ON decisions(last_reviewed_at)"
            )
            conn.commit()

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages:
            content = message.get("content")
            if content is None:
                continue
            if isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(str(block.get("text", "")))
                content = "\n".join(text_parts).strip()
            else:
                content = str(content).strip()
            if not content:
                continue
            tools = (
                f" [tools: {', '.join(message['tools_used'])}]"
                if message.get("tools_used")
                else ""
            )
            ts = str(message.get("timestamp", "?"))[:16]
            role = str(message.get("role", "?")).upper()
            lines.append(f"[{ts}] {role}{tools}: {content}")
        return "\n".join(lines)

    @staticmethod
    def _decision_to_rag_document(d: Decision) -> str:
        """Canonical text block for LightRAG ainsert (proposal §2.4 style)."""
        reasons = "; ".join(d.reasons) if d.reasons else "(none)"
        objections = "; ".join(d.objections) if d.objections else "(none)"
        alts = "; ".join(d.alternatives) if d.alternatives else "(none)"
        people = "; ".join(d.participants) if d.participants else "(unknown)"
        return (
            f"[DECISION {d.id}] topic={d.topic}\n"
            f"statement: {d.statement}\n"
            f"reasons: {reasons}\n"
            f"objections: {objections}\n"
            f"alternatives: {alts}\n"
            f"participants: {people}\n"
            f"decided_at: {d.decided_at}\n"
            f"project: {d.project}\n"
            f"importance: {d.importance}\n"
        )

    def _row_to_decision(self, row: sqlite3.Row) -> Decision:
        return Decision(
            id=row["id"],
            project=row["project"],
            topic=row["topic"],
            statement=row["statement"],
            reasons=json.loads(row["reasons"]),
            objections=json.loads(row["objections"]),
            alternatives=json.loads(row["alternatives"]),
            decided_at=row["decided_at"],
            deadline=row["deadline"],
            participants=json.loads(row["participants"]),
            source=cast(Any, row["source"]),
            source_ref=row["source_ref"],
            importance=row["importance"],
            last_reviewed_at=row["last_reviewed_at"],
            review_count=row["review_count"],
            strength=row["strength"],
            supersedes=row["supersedes"],
            status=cast(Any, row["status"]),
        )

    async def extract(
        self,
        messages: list[dict[str, Any]],
        *,
        project: str = "default",
    ) -> list[Decision]:
        """Run structured LLM extraction on *messages*; returns normalized `Decision` rows (not yet persisted)."""
        text = self._format_messages(messages)
        if not text.strip():
            return []

        user_prompt = (
            render_template("custom/decision_extract.md", strip=True)
            + "\n\n"
            + text
        )
        msg_list: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "You extract decision events into the required JSON schema only.",
            },
            {"role": "user", "content": user_prompt},
        ]

        self._provider.set_scheme(DecisionExtractResult)
        response = await self._provider.chat_scheme(
            msg_list,
            model=self._model,
            tools=None,
            tool_choice=None,
        )
        if isinstance(response, LLMResponse):
            logger.warning("Decision extract: LLM returned error response")
            return []

        parsed = cast(LLMResponseStructure, response).parsed
        if parsed is None:
            return []

        if isinstance(parsed, DecisionExtractResult):
            items = list(parsed.result)
        elif isinstance(parsed, dict):
            items = [DecisionExtractItem.model_validate(x) for x in parsed.get("result") or []]
        else:
            raw = getattr(parsed, "result", None)
            if raw is None:
                return []
            items = [DecisionExtractItem.model_validate(x) for x in raw]

        now = int(time.time())
        out: list[Decision] = []
        for it in items:
            if it.importance < self._IMPORTANCE_FLOOR:
                continue
            dec_id = uuid.uuid4().hex[:8]
            decided_at = it.decided_at if it.decided_at is not None else now
            out.append(
                Decision(
                    id=dec_id,
                    project=project,
                    topic=it.topic.strip(),
                    statement=it.statement.strip(),
                    reasons=list(it.reasons),
                    objections=list(it.objections),
                    alternatives=list(it.alternatives),
                    decided_at=decided_at,
                    deadline=it.deadline,
                    participants=list(it.participants),
                    source=it.source,
                    source_ref=it.source_ref.strip() if it.source_ref else "unknown",
                    importance=it.importance,
                    last_reviewed_at=now,
                    review_count=0,
                    strength=1.0,
                    supersedes=None,
                    status="active",
                )
            )
        return out

    def _upsert_sqlite(self, d: Decision) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decisions (
                    id, project, topic, statement, reasons, objections, alternatives,
                    decided_at, deadline, participants, source, source_ref, importance,
                    last_reviewed_at, review_count, strength, supersedes, status
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    d.id,
                    d.project,
                    d.topic,
                    d.statement,
                    d.reasons_json(),
                    d.objections_json(),
                    d.alternatives_json(),
                    d.decided_at,
                    d.deadline,
                    d.participants_json(),
                    d.source,
                    d.source_ref,
                    d.importance,
                    d.last_reviewed_at,
                    d.review_count,
                    d.strength,
                    d.supersedes,
                    d.status,
                ),
            )
            conn.commit()

    async def store(self, decisions: list[Decision]) -> None:
        """Persist decisions to SQLite and optionally insert into the shared LightRAG index."""
        for d in decisions:
            self._upsert_sqlite(d)

        rag = getattr(self._episodic, "_rag", None) if self._episodic is not None else None
        if rag is None:
            return

        for d in decisions:
            try:
                await rag.ainsert(self._decision_to_rag_document(d))
            except Exception:
                logger.exception("Decision store: LightRAG ainsert failed for id={}", d.id)

    def get(self, decision_id: str) -> Decision | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_decision(row)

    def has_for_project(self, project: str) -> bool:
        """Return True if there is at least one active decision row for *project*."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM decisions
                WHERE project = ? AND status = 'active'
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            return row is not None

    def list_by_project(self, project: str, *, limit: int = 50) -> list[Decision]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM decisions
                WHERE project = ? AND status = 'active'
                ORDER BY decided_at DESC
                LIMIT ?
                """,
                (project, limit),
            ).fetchall()
            return [self._row_to_decision(r) for r in rows]
