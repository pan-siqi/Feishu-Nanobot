#!/usr/bin/env python3
"""
E2E 抗干扰基准（submission_report_final.md §5.1）

真实链路：DecisionMemoryStore.extract → PostgreSQL → build_embed → retrieve。
需：PostgreSQL（NANOBOT_PG_*）、OPENAI_API_KEY（或 NANOBOT_BENCHMARK_OPENAI_API_KEY）、
仓库根目录下 model/bge-small-zh-v1.5（或 HF 自动拉取）。

用法（在仓库根目录）:
  uv run python test_pipeline/e2e_noise.py
  NANOBOT_BENCHMARK_NOISE_LIMIT=50 uv run python test_pipeline/e2e_noise.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.chdir(_REPO)

from test_pipeline.helpers import load_dataset_json
from test_pipeline.runtime import (
    benchmark_openai_provider,
    connect_session,
    decision_hit,
    delete_project_rows,
    history_from_texts,
    make_benchmark_context,
)


async def run_noise_e2e(*, noise_limit: int | None, skip_cleanup: bool) -> int:
    benchmark_openai_provider()

    data = load_dataset_json("noise_robustness", "fixture.json")
    meta = data["meta"]
    project = meta["project"]
    queries: list[str] = meta["queries"]
    hit_subs: list[str] = meta["hit_substrings"]

    signals: list[str] = list(data["signal_messages"])
    noise: list[str] = list(data["noise_messages"])
    if noise_limit is not None:
        noise = noise[:noise_limit]

    texts = signals + noise
    history = history_from_texts(texts, id_prefix="bench")

    ctx = make_benchmark_context(project)
    try:
        await ctx.store.extract(history, project=project)
        ctx.repo.build_embed()

        rows = ctx.repo.list(limit=50, project=project)
        print(f"=== E2E Noise (§5.1) project={project!r} ===")
        print(f"messages_injected: signal={len(signals)} noise={len(noise)} total={len(texts)}")
        print(f"ec_rows_in_db: {len(rows)}")
        for r in rows[:5]:
            print(f"  - {r.ec_id} status={r.status} result_preview={r.decision_result[:60]!r}...")

        use_filter = os.environ.get("NANOBOT_BENCHMARK_RETRIEVE_FILTER", "1") not in ("0", "false", "False")
        hit1 = hit3 = 0
        top1_dists: list[float] = []
        for q in queries:
            hits = ctx.repo.retrieve(q, top_k=3, is_filter=use_filter, project=project)
            if not hits and use_filter:
                hits = ctx.repo.retrieve(q, top_k=3, is_filter=False, project=project)
            if not hits:
                print(f"Q empty: {q!r}")
                continue
            d1 = hits[0][0].decision_result
            top1_dists.append(float(hits[0][1]))
            if decision_hit(d1, hit_subs):
                hit1 += 1
            if any(decision_hit(h[0].decision_result, hit_subs) for h in hits[:3]):
                hit3 += 1

        nq = len(queries)
        print(f"retrieve_is_filter: {use_filter}")
        print(f"Hit@1: {hit1}/{nq}")
        print(f"Hit@3: {hit3}/{nq}")
        if top1_dists:
            print(f"avg_top1_cosine_distance: {sum(top1_dists) / len(top1_dists):.4f}")

        ok = hit1 >= max(1, int(0.5 * nq)) and hit3 >= max(1, int(0.67 * nq))
        if not ok:
            print("WARN: below report targets (Hit@1>=50% Hit@3>=67%)", file=sys.stderr)
            return 2
        return 0
    finally:
        if not skip_cleanup:
            delete_project_rows(ctx.session, project)
        ctx.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--noise-limit",
        type=int,
        default=None,
        help="truncate noise messages (default: all in fixture)",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="do not delete benchmark rows after run (for inspection)",
    )
    args = parser.parse_args()
    lim = args.noise_limit
    if lim is None and os.environ.get("NANOBOT_BENCHMARK_NOISE_LIMIT"):
        lim = int(os.environ["NANOBOT_BENCHMARK_NOISE_LIMIT"])

    try:
        from sqlalchemy import text

        s = connect_session()
        s.execute(text("SELECT 1"))
        s.commit()
        s.close()
    except Exception as exc:
        print(f"FAIL: database: {exc}", file=sys.stderr)
        return 3

    return asyncio.run(run_noise_e2e(noise_limit=lim, skip_cleanup=args.keep_data))


if __name__ == "__main__":
    raise SystemExit(main())
