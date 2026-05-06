"""Build and normalize Feishu interactive card payloads for IM messages.

Supports:
- Raw card JSON (schema 1.x with root ``elements`` or schema 2.0 with ``body.elements``)
- Markdown string → schema 2.0 card with a single ``markdown`` element
- Optional file path (UTF-8 text) with the same rules as inline payload

Schema 2.0 layout follows Feishu docs (``body.elements``, ``config.update_multi``).
See: https://open.feishu.cn/document/feishu-cards/card-json-v2-breaking-changes-release-notes
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

PayloadFormat = Literal["auto", "json", "markdown"]

_CARD_PAYLOAD_FORMAT_KEY = "_card_payload_format"
_CARD_PAYLOAD_KEY = "_card_payload"
_CARD_PAYLOAD_PATH_KEY = "_card_payload_path"
_CARD_JSON_KEY = "_card_json"


def markdown_to_card_v2(
    markdown: str,
    *,
    header_title: str | None = None,
    header_template: str = "blue",
) -> dict[str, Any]:
    """Wrap markdown in a schema 2.0 interactive card."""
    text = markdown.strip()
    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "update_multi": True},
        "body": {"elements": [{"tag": "markdown", "content": text}]},
    }
    if header_title:
        card["header"] = {
            "template": header_template,
            "title": {"tag": "plain_text", "content": header_title},
        }
    return card


def _looks_like_json_object(s: str) -> bool:
    t = s.lstrip()
    return bool(t) and t[0] == "{"


def parse_card_payload_string(raw: str, fmt: PayloadFormat = "auto") -> dict[str, Any]:
    """Parse inline text as JSON card or markdown."""
    stripped = raw.strip()
    if not stripped:
        raise ValueError("card payload is empty")

    if fmt == "markdown":
        return markdown_to_card_v2(stripped)

    if fmt == "json":
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise TypeError("card JSON must be an object at the root")
        return normalize_interactive_card(data)

    # auto
    if _looks_like_json_object(stripped):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                return normalize_interactive_card(data)
        except json.JSONDecodeError:
            pass
    return markdown_to_card_v2(stripped)


def load_card_payload_file(path: str | Path, fmt: PayloadFormat = "auto") -> dict[str, Any]:
    p = Path(path).expanduser()
    text = p.read_text(encoding="utf-8")
    return parse_card_payload_string(text, fmt=fmt)


def normalize_interactive_card(card: dict[str, Any]) -> dict[str, Any]:
    """Ensure dict is suitable for ``msg_type=interactive`` (schema 2.0 shape).

    - Schema 2.0: merge defaults on ``config``, ensure ``body.elements`` exists.
    - Schema 1.x / legacy: root ``elements`` → moved under ``body``; ``schema`` set to 2.0.
    """
    if not isinstance(card, dict):
        raise TypeError("card must be a dict")

    out = copy.deepcopy(card)
    schema = out.get("schema")

    if schema == "2.0" or "body" in out:
        out.setdefault("schema", "2.0")
        body = out.get("body")
        if not isinstance(body, dict):
            body = {}
            out["body"] = body
        els = body.get("elements")
        if not isinstance(els, list):
            els = []
        body["elements"] = els
        cfg = dict(out.get("config") or {})
        cfg.setdefault("update_multi", True)
        cfg.setdefault("wide_screen_mode", True)
        out["config"] = cfg
        return out

    # Legacy: top-level elements (1.x)
    elements = out.pop("elements", None)
    if not isinstance(elements, list):
        elements = []
    out.pop("i18n_elements", None)
    cfg = dict(out.pop("config", None) or {})
    cfg.setdefault("wide_screen_mode", True)
    header = out.pop("header", None)
    card_link = out.pop("card_link", None)
    # Remaining keys (e.g. header overrides) — re-apply known top-level fields
    merged: dict[str, Any] = {
        "schema": "2.0",
        "config": {**cfg, "update_multi": True},
        "body": {"elements": elements},
    }
    if header is not None:
        merged["header"] = header
    if card_link is not None:
        merged["card_link"] = card_link
    for key, val in out.items():
        if key in ("schema", "config", "body"):
            continue
        merged[key] = val
    return merged


def _coerce_payload_format(value: Any) -> PayloadFormat:
    if value is None:
        return "auto"
    s = str(value).strip().lower()
    if s == "json":
        return "json"
    if s == "markdown":
        return "markdown"
    return "auto"


def resolve_interactive_card(
    metadata: dict[str, Any] | None,
    *,
    default_markdown: str | None = None,
    default_header_title: str | None = "Nanobot",
) -> dict[str, Any]:
    """Pick card content from message metadata with a fixed precedence.

    Precedence:
    1. ``_card_json`` — already a dict (normalized to 2.0)
    2. ``_card_payload_path`` — file contents
    3. ``_card_payload`` — str (markdown or JSON) or dict (card object)
    4. ``default_markdown`` — demo / fallback markdown

    ``_card_payload_format``: ``auto`` | ``json`` | ``markdown``
    """
    meta = dict(metadata or {})
    fmt = _coerce_payload_format(meta.get(_CARD_PAYLOAD_FORMAT_KEY))

    if _CARD_JSON_KEY in meta:
        raw = meta[_CARD_JSON_KEY]
        if isinstance(raw, dict):
            return normalize_interactive_card(raw)
        if isinstance(raw, str) and raw.strip():
            return parse_card_payload_string(raw, fmt="json")

    path_val = meta.get(_CARD_PAYLOAD_PATH_KEY)
    if path_val:
        return load_card_payload_file(str(path_val), fmt=fmt)

    payload = meta.get(_CARD_PAYLOAD_KEY)
    if isinstance(payload, dict):
        return normalize_interactive_card(payload)
    if isinstance(payload, str) and payload.strip():
        return parse_card_payload_string(payload, fmt=fmt)

    if default_markdown and default_markdown.strip():
        return markdown_to_card_v2(
            default_markdown,
            header_title=default_header_title,
        )

    return markdown_to_card_v2(
        "_Empty card_",
        header_title=default_header_title,
    )
