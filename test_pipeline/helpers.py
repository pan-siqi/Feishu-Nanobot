"""Shared helpers for DecisionMind benchmark pipelines (report §5)."""

from __future__ import annotations

import json
import uuid
from dataclasses import fields
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from nanobot.agent.hiarch_memory.database.ec_database import EventCandidateMetaClass
from nanobot.utils.prompt_templates import render_template

REPO_ROOT = Path(__file__).resolve().parents[1]
_PIPELINE_DIR = Path(__file__).resolve().parent

# Report-aligned datasets live under fixtures/report/ (see README-test.md).
REPORT_FIXTURES_DIR = _PIPELINE_DIR / "fixtures" / "report"
# Back-compat alias: historical scripts used `data/`.
DATA_DIR = REPORT_FIXTURES_DIR
_LEGACY_DATA_DIR = _PIPELINE_DIR / "data"


def report_fixture_path(*parts: str) -> Path:
    return REPORT_FIXTURES_DIR.joinpath(*parts)


def load_dataset_json(*parts: str) -> Any:
    path = REPORT_FIXTURES_DIR.joinpath(*parts)
    if not path.exists() and _LEGACY_DATA_DIR.exists():
        alt = _LEGACY_DATA_DIR.joinpath(*parts)
        if alt.exists():
            path = alt
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_scenario_json(name: str) -> Any:
    """Load `fixtures/scenarios/{name}.json` (router / extended benchmarks)."""
    path = _PIPELINE_DIR / "fixtures" / "scenarios" / f"{name}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_embedding_model() -> SentenceTransformer:
    local = REPO_ROOT / "model" / "bge-small-zh-v1.5"
    if local.exists():
        return SentenceTransformer(str(local))
    return SentenceTransformer("BAAI/bge-small-zh-v1.5")


_embed_singleton: SentenceTransformer | None = None


def load_embedding_model_cached() -> SentenceTransformer:
    global _embed_singleton
    if _embed_singleton is None:
        _embed_singleton = load_embedding_model()
    return _embed_singleton


def meta_to_canonical_text(ec: EventCandidateMetaClass) -> str:
    _dict = {f.name: getattr(ec, f.name) for f in fields(EventCandidateMetaClass)}
    return render_template("custom/canonical.md", strip=True, **_dict)


def new_ec_id() -> str:
    return f"ec_{uuid.uuid4().hex[:10]}"


def meta_from_partial(project: str, partial: dict[str, Any], ec_id: str | None = None) -> EventCandidateMetaClass:
    now = "2026-05-07T00:00:00+00:00"
    base = {
        "ec_id": ec_id or new_ec_id(),
        "event_name": partial.get("event_name", "event"),
        "aliases": partial.get("aliases", []),
        "decision_signal": partial.get("decision_signal", "decided"),
        "summary": partial.get("summary", ""),
        "decision_result": partial.get("decision_result", ""),
        "entities": partial.get("entities", []),
        "evidence_message_ids": partial.get("evidence_message_ids", ["m_x"]),
        "confidence": float(partial.get("confidence", 0.8)),
        "update_at": partial.get("update_at", now),
        "project": project,
        "reasons": partial.get("reasons", []),
        "objections": partial.get("objections", []),
        "alternatives": partial.get("alternatives", []),
        "deadline": partial.get("deadline"),
        "participants": partial.get("participants", []),
        "importance": float(partial.get("importance", 0.6)),
        "strength": float(partial.get("strength", 10.0)),
        "last_reviewed_at": partial.get("last_reviewed_at"),
        "review_count": int(partial.get("review_count", 0)),
        "status": partial.get("status", "active"),
        "supersedes": partial.get("supersedes"),
    }
    return EventCandidateMetaClass(**base)


def cosine_distance_matrix(query_norm: np.ndarray, docs_norm: np.ndarray) -> np.ndarray:
    """query_norm: (d,), docs_norm: (n, d) — vectors L2-normalized. Returns (n,) cosine distance."""
    sim = docs_norm @ query_norm
    return 1.0 - sim


def hit_decision(decision_result: str, substrings: list[str]) -> bool:
    t = decision_result
    return any(s in t for s in substrings)
