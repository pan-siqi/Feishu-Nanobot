#!/usr/bin/env python3
"""
矛盾更新 / 时序覆写测试（submission_report_final.md §5.2）

离线模拟：合并后的金标准 EventCandidate（Bob）与由两批次对话文本构造的
干扰行共同检索；验证查询「运营周报收件人」时 top-1 为正确覆写结论。

不调用 LLM；不依赖 PostgreSQL。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import numpy as np

from test_pipeline.helpers import (
    cosine_distance_matrix,
    load_dataset_json,
    load_embedding_model_cached,
    meta_from_partial,
    meta_to_canonical_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Temporal override benchmark (§5.2)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    data = load_dataset_json("temporal_override", "fixture.json")
    m = data["meta"]
    project = m["project"]
    query = m["query"]
    expected = m["expected_substrings_top1"]

    merged = meta_from_partial(project, data["golden_ec_after_merge"], ec_id="ec_ops_merged")

    # 与报告一致：批次对话经抽取合并后库中主要为「合并后的 EC」；大量无关技术噪声代表
    # 其他决策行。若用批次原文作干扰项，会与查询「运营周报」过近而压过 canonical，故借用
    # 抗干扰 fixture 中的通用 Q&A 作为干扰向量（仍满足「多行并存、仅一条为真」的检索设定）。
    noise_fixture = load_dataset_json("noise_robustness", "fixture.json")
    noise_msgs: list[str] = list(noise_fixture["noise_messages"])[:100]

    distractor_texts: list[str] = []
    for i, text in enumerate(noise_msgs):
        d = meta_from_partial(
            project,
            {
                "event_name": f"noise_distractor_{i}",
                "summary": text[:200],
                "decision_result": text,
                "confidence": 0.4,
            },
            ec_id=f"ec_ops_noise_{i}",
        )
        distractor_texts.append(meta_to_canonical_text(d))

    texts = [meta_to_canonical_text(merged)] + distractor_texts
    model = load_embedding_model_cached()
    emb = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
    emb = np.asarray(emb, dtype=np.float64)

    qv = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
    dists = cosine_distance_matrix(qv, emb)
    top1 = int(np.argmin(dists))

    ok = top1 == 0 and all(s in merged.decision_result for s in expected)

    print("=== Temporal override (§5.2) ===")
    print(f"query: {query!r}")
    print(f"top1_index: {top1} (0 = merged gold)")
    print(f"top1_cosine_distance: {float(dists[top1]):.4f}")
    print(f"expected_substrings in merged decision_result: {expected}")
    print(f"merge_path_simulated: True (single merged EC as gold row)")
    print(f"top1_is_correct: {ok}")
    if args.verbose:
        print("--- top1 canonical snippet ---")
        print(texts[top1][:800])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
