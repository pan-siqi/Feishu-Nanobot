#!/usr/bin/env python3
"""
估算「全量历史注入」vs「短查询 + 决策记忆块」的 Token 量级（报告 §5.3 / Scorecard Token 节省）。

不调用 API：用 tiktoken cl100k_base 对文本计数；记忆侧用 golden_decision 的 canonical 文本 × top_k。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import tiktoken

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from test_pipeline.helpers import (
    load_dataset_json,
    meta_from_partial,
    meta_to_canonical_text,
)


def _count(enc: tiktoken.Encoding, text: str) -> int:
    return len(enc.encode(text or ""))


def main() -> int:
    enc = tiktoken.get_encoding("cl100k_base")
    noise_data = load_dataset_json("noise_robustness", "fixture.json")
    project = noise_data["meta"]["project"]
    texts = list(noise_data["signal_messages"]) + list(noise_data["noise_messages"])
    naive_transcript = "\n".join(f"[user]: {t}" for t in texts)
    naive_tokens = _count(enc, naive_transcript)

    gold = meta_from_partial(project, noise_data["golden_decision"], ec_id="ec_gold")
    canon = meta_to_canonical_text(gold)
    top_k = int(os.environ.get("NANOBOT_BENCHMARK_TOP_K", "3"))
    memory_block = ("## Related decisions\n\n" + (canon + "\n\n") * top_k).strip()
    memory_tokens = _count(enc, memory_block)

    queries = list(noise_data["meta"]["queries"])
    avg_query = queries[len(queries) // 2]
    with_memory_tokens = _count(enc, avg_query) + memory_tokens

    if naive_tokens == 0:
        print("no content")
        return 1
    saved = 1.0 - with_memory_tokens / naive_tokens
    print("=== Token budget estimate (report-style) ===")
    print(f"naive_full_history_tokens (~{len(texts)} msgs): {naive_tokens}")
    print(f"memory_inject_block_tokens (top_k={top_k}): {memory_tokens}")
    print(f"sample_query_tokens: {_count(enc, avg_query)}")
    print(f"with_memory_turn_tokens (query+block): {with_memory_tokens}")
    print(f"estimated_token_saving_ratio: {100.0 * saved:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
