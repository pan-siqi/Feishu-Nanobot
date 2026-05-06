#!/usr/bin/env python3
"""
E2E 矛盾更新 / 时序覆写（submission_report_final.md §5.2）

真实链路：批次 A extract → 批次 B extract（走 retrieve + evaluate + merge）→ retrieve。

依赖同 e2e_noise.py（PostgreSQL、LLM、bge）。

用法:
  uv run python test_pipeline/e2e_temporal.py
  uv run python test_pipeline/e2e_temporal.py --keep-data
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.chdir(_REPO)

from test_pipeline.helpers import load_dataset_json
from test_pipeline.runtime import (
    batched_decision_extract,
    benchmark_openai_provider,
    connect_session,
    decision_hit,
    delete_project_rows,
    init_decision_schema,
    make_benchmark_context,
)


async def run_temporal_e2e(*, skip_cleanup: bool, window_size: int, overlap: int) -> int:
    data = load_dataset_json("temporal_override", "fixture.json")
    m = data["meta"]
    project = m["project"]
    query = m["query"]
    expected = list(m["expected_substrings_top1"])

    batch_a = list(data["batch_a_messages"])
    batch_b = list(data["batch_b_messages"])
    week1 = datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc)
    week2 = week1 + timedelta(days=7)

    max_score = float(os.environ.get("NANOBOT_BENCHMARK_MAX_SCORE", "0.5"))
    ctx = make_benchmark_context(project, max_score=max_score)
    try:
        await batched_decision_extract(
            ctx.store,
            batch_a,
            project,
            window_size=min(window_size, len(batch_a)),
            overlap=min(overlap, max(0, len(batch_a) - 1)),
            id_prefix="ops_a",
            start=week1,
        )
        await batched_decision_extract(
            ctx.store,
            batch_b,
            project,
            window_size=min(window_size, len(batch_b)),
            overlap=min(overlap, max(0, len(batch_b) - 1)),
            id_prefix="ops_b",
            start=week2,
        )
        ctx.repo.build_embed()

        rows = ctx.repo.list(limit=30, project=project)
        print(f"=== E2E Temporal override (§5.2) project={project!r} model={ctx.model!r} ===")
        print(f"batch_a_msgs={len(batch_a)} batch_b_msgs={len(batch_b)} ec_rows={len(rows)}")
        for r in rows[:10]:
            print(
                f"  - {r.ec_id} signal={r.decision_signal!r} status={r.status} "
                f"result={r.decision_result[:80]!r}..."
            )

        use_filter = os.environ.get("NANOBOT_BENCHMARK_RETRIEVE_FILTER", "1") not in ("0", "false", "False")
        hits = ctx.repo.retrieve(query, top_k=5, is_filter=use_filter, project=project)
        if not hits and use_filter:
            hits = ctx.repo.retrieve(query, top_k=5, is_filter=False, project=project)
        if not hits:
            print("FAIL: no retrieve hits", file=sys.stderr)
            return 2

        top1 = hits[0][0].decision_result
        dist = float(hits[0][1])
        ok = all(s in top1 for s in expected) and decision_hit(top1, ["Bob", "bob"])
        # 覆写后 top-1 不应仍是「仅发给 Alice」的旧结论
        only_alice = (
            "alice@team.com" in top1.lower()
            and "bob" not in top1.lower()
            and "bob@team.com" not in top1.lower()
        )

        print(f"query: {query!r}")
        print(f"top1_cosine_distance: {dist:.4f}")
        print(f"top1_decision_result: {top1[:200]!r}...")
        print(f"expected_substrings_present: {ok}")
        print(f"only_alice_top1: {only_alice}")

        if only_alice or not ok:
            print("WARN: merge or retrieval did not match report expectations", file=sys.stderr)
            return 2
        return 0
    finally:
        if not skip_cleanup:
            delete_project_rows(ctx.session, project)
        ctx.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--overlap", type=int, default=20)
    args = parser.parse_args()

    try:
        from sqlalchemy import text

        s = connect_session()
        init_decision_schema(s)
        s.execute(text("SELECT 1"))
        s.commit()
        s.close()
    except Exception as exc:
        print(f"FAIL: database: {exc}", file=sys.stderr)
        return 3

    try:
        benchmark_openai_provider()
    except RuntimeError as exc:
        print(f"FAIL: llm: {exc}", file=sys.stderr)
        return 4

    return asyncio.run(
        run_temporal_e2e(
            skip_cleanup=args.keep_data,
            window_size=args.window_size,
            overlap=args.overlap,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
