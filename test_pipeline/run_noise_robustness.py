#!/usr/bin/env python3
"""
抗干扰测试（submission_report_final.md §5.1）

离线模拟 pgvector 余弦检索：1 条金标准 EventCandidate + N 条由噪声消息构造的
干扰候选，对 6 个查询计算 Hit@1 / Hit@3 与平均 top-1 余弦距离。

不调用 LLM；依赖 sentence-transformers（与生产一致的 bge-small-zh-v1.5）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 从仓库根目录导入 nanobot
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import numpy as np

from test_pipeline.helpers import (
    cosine_distance_matrix,
    hit_decision,
    load_dataset_json,
    load_embedding_model_cached,
    meta_from_partial,
    meta_to_canonical_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Noise robustness benchmark (§5.1)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    data = load_dataset_json("noise_robustness", "fixture.json")
    meta = data["meta"]
    project = meta["project"]
    queries: list[str] = meta["queries"]
    hit_subs: list[str] = meta["hit_substrings"]

    gold = meta_from_partial(project, data["golden_decision"], ec_id="ec_noise_gold")
    gold_text = meta_to_canonical_text(gold)

    distractor_texts: list[str] = []
    distractor_results: list[str] = []
    for i, noise in enumerate(data["noise_messages"]):
        d = meta_from_partial(
            project,
            {
                "event_name": f"noise_qa_{i}",
                "summary": noise[:240],
                "decision_result": noise,
                "decision_signal": "decided",
                "confidence": 0.5,
                "entities": [],
                "reasons": [],
            },
            ec_id=f"ec_noise_distractor_{i}",
        )
        distractor_texts.append(meta_to_canonical_text(d))
        distractor_results.append(d.decision_result)

    all_texts = [gold_text] + distractor_texts
    model = load_embedding_model_cached()
    emb = model.encode(all_texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    emb = np.asarray(emb, dtype=np.float64)
    gold_idx = 0

    hit1 = 0
    hit3 = 0
    top1_distances: list[float] = []

    for q in queries:
        qv = model.encode([q], normalize_embeddings=True, show_progress_bar=False)[0]
        dists = cosine_distance_matrix(qv, emb)
        order = np.argsort(dists)
        top1_i = int(order[0])
        top3 = [int(order[j]) for j in range(min(3, len(order)))]

        def decision_at(idx: int) -> str:
            return gold.decision_result if idx == gold_idx else distractor_results[idx - 1]

        top1_distances.append(float(dists[top1_i]))
        ok1 = hit_decision(decision_at(top1_i), hit_subs)
        ok3 = any(hit_decision(decision_at(j), hit_subs) for j in top3)

        if ok1:
            hit1 += 1
        if ok3:
            hit3 += 1
        if args.verbose:
            print(f"Q: {q!r}\n  top1_idx={top1_i} dist={dists[top1_i]:.4f} hit@1={ok1} hit@3={ok3}")

    nq = len(queries)
    print("=== Noise robustness (§5.1) ===")
    print(f"signal_messages: {len(data['signal_messages'])}")
    print(f"noise_messages: {len(data['noise_messages'])}")
    print(f"noise_ratio: {len(data['noise_messages']) / (len(data['signal_messages']) + len(data['noise_messages'])):.1%}")
    print(f"Hit@1: {hit1}/{nq} = {100.0 * hit1 / nq:.1f}%")
    print(f"Hit@3: {hit3}/{nq} = {100.0 * hit3 / nq:.1f}%")
    print(f"Avg top-1 cosine distance: {float(np.mean(top1_distances)):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
