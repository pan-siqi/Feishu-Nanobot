"""Structured decision memory: extract (LLM + schema), store (SQLite + optional LightRAG)."""

from __future__ import annotations

import json
import math
import re
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
    _TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")

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

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join((text or "").strip().lower().split())

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        return {m.group(0).lower() for m in cls._TOKEN_RE.finditer(text or "")}

    @classmethod
    def _same_statement(cls, left: str, right: str) -> bool:
        return cls._normalize_text(left) == cls._normalize_text(right)

    def _score_recall(self, d: Decision, query: str, now_ts: int) -> float:
        """Simple, deterministic scoring for recall ranking."""
        qn = self._normalize_text(query)
        q_tokens = self._tokenize(query)
        haystack = " ".join([d.topic, d.statement, " ".join(d.reasons), " ".join(d.objections)])
        haystack_norm = self._normalize_text(haystack)
        haystack_tokens = self._tokenize(haystack)

        lex = 0.0
        if qn:
            if qn in haystack_norm:
                lex += 1.0
            if qn in self._normalize_text(d.topic):
                lex += 0.5
        if q_tokens:
            overlap = len(q_tokens & haystack_tokens)
            lex += overlap / max(len(q_tokens), 1)
        lex = min(2.0, lex) / 2.0  # normalize to [0, 1]

        age_days = max(0.0, (now_ts - d.decided_at) / 86400.0)
        freshness = math.exp(-age_days / 45.0)  # recent items get a mild boost

        strength_norm = max(0.0, min(1.0, d.strength / 2.0))
        score = 0.45 * lex + 0.30 * d.importance + 0.15 * strength_norm + 0.10 * freshness
        return score

    def _mark_status(self, decision_id: str, status: Literal["active", "superseded", "expired"]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE decisions SET status = ? WHERE id = ?",
                (status, decision_id),
            )
            conn.commit()

    def _set_active_status_for_topic(self, *, project: str, topic: str, except_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE decisions
                SET status = 'superseded'
                WHERE project = ?
                  AND topic = ?
                  AND status = 'active'
                  AND id != ?
                """,
                (project, topic, except_id),
            )
            conn.commit()

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

    def _find_active_same_topic(self, project: str, topic: str) -> list[Decision]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM decisions
                WHERE project = ? AND topic = ? AND status = 'active'
                ORDER BY decided_at DESC
                """,
                (project, topic),
            ).fetchall()
        return [self._row_to_decision(r) for r in rows]

    async def store(self, decisions: list[Decision]) -> None:
        """Persist decisions to SQLite and optionally insert into the shared LightRAG index."""
        to_insert_rag: list[Decision] = []
        for d in decisions:
            existing_same_topic = self._find_active_same_topic(d.project, d.topic)
            merged_existing: Decision | None = None
            if existing_same_topic:
                for old in existing_same_topic:
                    if self._same_statement(old.statement, d.statement):
                        # Deduplicate by merging onto the existing active row.
                        old.reasons = list(dict.fromkeys([*old.reasons, *d.reasons]))
                        old.objections = list(dict.fromkeys([*old.objections, *d.objections]))
                        old.alternatives = list(dict.fromkeys([*old.alternatives, *d.alternatives]))
                        old.participants = list(dict.fromkeys([*old.participants, *d.participants]))
                        old.importance = max(old.importance, d.importance)
                        old.last_reviewed_at = int(time.time())
                        merged_existing = old
                        break

            if merged_existing is not None:
                self._upsert_sqlite(merged_existing)
                continue

            # New statement on same topic supersedes prior active records.
            if existing_same_topic:
                d.supersedes = existing_same_topic[0].id
            self._set_active_status_for_topic(project=d.project, topic=d.topic, except_id=d.id)
            self._upsert_sqlite(d)
            to_insert_rag.append(d)

        rag = getattr(self._episodic, "_rag", None) if self._episodic is not None else None
        if rag is None:
            return

        for d in to_insert_rag:
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

    def list_projects(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT project FROM decisions ORDER BY project ASC"
            ).fetchall()
        return [str(r["project"]) for r in rows if r["project"]]

    def recall(self, query: str, *, project: str, limit: int = 8) -> list[Decision]:
        """Query-aware recall on active decisions within a project."""
        rows = self.list_by_project(project, limit=200)
        if not rows:
            return []
        now = int(time.time())
        scored = [(self._score_recall(d, query, now), d) for d in rows]
        scored.sort(key=lambda x: (x[0], x[1].decided_at), reverse=True)
        out = [d for _, d in scored[:limit]]
        return out

    def decay(self, *, now_ts: int | None = None, half_life_days: float = 14.0) -> int:
        """Decay strength for active decisions based on last reviewed time."""
        now = int(time.time()) if now_ts is None else int(now_ts)
        updated = 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE status = 'active'"
            ).fetchall()
            for row in rows:
                d = self._row_to_decision(row)
                age_days = max(0.0, (now - d.last_reviewed_at) / 86400.0)
                reviewed_bonus = 1.0 + min(1.0, d.review_count / 10.0)
                decayed = reviewed_bonus * (0.5 ** (age_days / max(half_life_days, 1e-6)))
                new_strength = max(0.1, min(2.0, decayed))
                if abs(new_strength - d.strength) >= 1e-6:
                    conn.execute(
                        "UPDATE decisions SET strength = ? WHERE id = ?",
                        (new_strength, d.id),
                    )
                    updated += 1
            conn.commit()
        return updated

    def list_review_candidates(
        self,
        *,
        project: str | None = None,
        limit: int = 8,
        now_ts: int | None = None,
    ) -> list[Decision]:
        """Pick decisions that are important but stale for review reminders."""
        now = int(time.time()) if now_ts is None else int(now_ts)
        query = "SELECT * FROM decisions WHERE status = 'active'"
        params: list[Any] = []
        if project:
            query += " AND project = ?"
            params.append(project)
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        items = [self._row_to_decision(r) for r in rows]
        if not items:
            return []

        def urgency(d: Decision) -> float:
            stale_days = max(0.0, (now - d.last_reviewed_at) / 86400.0)
            stale_score = min(1.0, stale_days / 21.0)
            weak_score = 1.0 - max(0.0, min(1.0, d.strength / 2.0))
            return 0.50 * d.importance + 0.35 * stale_score + 0.15 * weak_score

        items.sort(key=lambda d: (urgency(d), d.decided_at), reverse=True)
        return items[:limit]

    def mark_review(
        self,
        decision_id: str,
        action: Literal["reinforce", "expire", "update"],
        *,
        new_statement: str | None = None,
    ) -> Decision | None:
        """Apply review feedback from user/channel interaction."""
        current = self.get(decision_id)
        if current is None:
            return None
        now = int(time.time())

        if action == "reinforce":
            current.review_count += 1
            current.last_reviewed_at = now
            current.strength = min(2.0, current.strength + 0.25)
            self._upsert_sqlite(current)
            return current

        if action == "expire":
            current.status = "expired"
            current.last_reviewed_at = now
            self._upsert_sqlite(current)
            return current

        if action == "update":
            statement = (new_statement or "").strip()
            if not statement:
                return None
            current.status = "superseded"
            current.last_reviewed_at = now
            self._upsert_sqlite(current)
            replacement = Decision(
                id=uuid.uuid4().hex[:8],
                project=current.project,
                topic=current.topic,
                statement=statement,
                reasons=list(current.reasons),
                objections=list(current.objections),
                alternatives=list(current.alternatives),
                decided_at=now,
                deadline=current.deadline,
                participants=list(current.participants),
                source="manual",
                source_ref=f"review:{decision_id}",
                importance=current.importance,
                last_reviewed_at=now,
                review_count=current.review_count + 1,
                strength=min(2.0, current.strength + 0.1),
                supersedes=current.id,
                status="active",
            )
            self._upsert_sqlite(replacement)
            return replacement
        return None
