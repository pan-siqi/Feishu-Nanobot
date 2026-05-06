#!/usr/bin/env python3
"""
Router 全链路 E2E：`.history.jsonl` → Router.operate_batch（Episodic LightRAG + Neo4j + Decision PG）。

对齐报告 §5「经 Router 卸批」叙述；需 PostgreSQL(pgvector)、Neo4j(NEO4J_*)、LLM、bge。

默认 `--suite smoke`（fixtures/scenarios/smoke_router.json）；`noise` / `temporal` 复用 fixtures/report 下报告数据集。

用法:
  uv run python test_pipeline/e2e_router_full.py
  uv run python test_pipeline/e2e_router_full.py --suite noise
  NANOBOT_MEMORY_ROUTE_ALL=1 uv run python test_pipeline/e2e_router_full.py
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

import jsonlines

from test_pipeline.helpers import load_dataset_json, load_scenario_json
from test_pipeline.runtime import (
    benchmark_openai_provider,
    connect_session,
    decision_hit,
    delete_project_rows,
    history_from_texts,
    init_decision_schema,
    make_router_pipeline_context,
)


def _write_history(path: str, rows: list[dict]) -> None:
    with jsonlines.open(path, mode="w") as writer:
        writer.write_all(rows)


async def _run_async(
    *,
    suite: str,
    keep_data: bool,
    noise_limit: int | None,
    check_aggregation: bool,
) -> int:
    # 确保聚合层会拉决策记忆（与默认 QueryRouter「仅 episodic」区分）
    os.environ.setdefault("NANOBOT_MEMORY_ROUTE_ALL", "1")

    max_score = float(os.environ.get("NANOBOT_BENCHMARK_MAX_SCORE", "0.5"))
    use_filter = os.environ.get("NANOBOT_BENCHMARK_RETRIEVE_FILTER", "1") not in ("0", "false", "False")

    if suite == "smoke":
        data = load_scenario_json("smoke_router")
        project = data["meta"]["project"]
        msgs = list(data["messages"])
        hist = history_from_texts(msgs, id_prefix="smoke")
        queries_meta = list(data["queries"])
    elif suite == "noise":
        raw = load_dataset_json("noise_robustness", "fixture.json")
        project = raw["meta"]["project"]
        sig = list(raw["signal_messages"])
        noise = list(raw["noise_messages"])
        if noise_limit is not None:
            noise = noise[:noise_limit]
        hist = history_from_texts(sig + noise, id_prefix="router_noise")
        queries_meta = [{"text": q, "hit_substrings": raw["meta"]["hit_substrings"]} for q in raw["meta"]["queries"]]
    elif suite == "temporal":
        raw = load_dataset_json("temporal_override", "fixture.json")
        project = raw["meta"]["project"]
        week1 = datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc)
        week2 = week1 + timedelta(days=7)
        ha = history_from_texts(list(raw["batch_a_messages"]), id_prefix="ta", start=week1)
        hb = history_from_texts(list(raw["batch_b_messages"]), id_prefix="tb", start=week2)
        hist = ha + hb
        q = raw["meta"]["query"]
        exp = list(raw["meta"]["expected_substrings_top1"])
        queries_meta = [{"text": q, "hit_substrings": exp, "temporal": True}]
    else:
        print(f"unknown suite: {suite}", file=sys.stderr)
        return 2

    ctx = make_router_pipeline_context(project, max_score=max_score)
    try:
        _write_history(ctx.history_save_path, hist)

        try:
            await ctx.episodic.initial_lightrag()
        except Exception as exc:
            print(f"FAIL: LightRAG/Neo4j 初始化: {exc}", file=sys.stderr)
            print("提示: 配置 NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD，并确保库可连。", file=sys.stderr)
            return 6

        await ctx.router.operate_batch(project=project)
        ctx.repo.build_embed()

        rows = ctx.repo.list(limit=50, project=project)
        print(f"=== E2E Router full suite={suite!r} project={project!r} model={ctx.model!r} ===")
        print(f"history_messages={len(hist)} ec_rows={len(rows)}")
        for r in rows[:6]:
            print(f"  ec {r.ec_id} status={r.status} preview={r.decision_result[:72]!r}...")

        if suite == "temporal":
            q0 = queries_meta[0]
            hits = ctx.repo.retrieve(q0["text"], top_k=3, is_filter=use_filter, project=project)
            if not hits and use_filter:
                hits = ctx.repo.retrieve(q0["text"], top_k=3, is_filter=False, project=project)
            if not hits:
                print("FAIL: temporal retrieve empty", file=sys.stderr)
                return 2
            top1 = hits[0][0].decision_result
            ok = all(s in top1 for s in q0["hit_substrings"]) and decision_hit(top1, ["Bob", "bob"])
            only_alice = (
                "alice@team.com" in top1.lower()
                and "bob" not in top1.lower()
                and "bob@team.com" not in top1.lower()
            )
            print(f"temporal top1_ok={ok} only_alice={only_alice}")
            if not ok or only_alice:
                return 2
            return 0

        # noise / smoke: 多 query
        nq = len(queries_meta)
        hit1 = hit3 = 0
        top1_dists: list[float] = []
        for qm in queries_meta:
            q = qm["text"]
            subs = list(qm["hit_substrings"])
            hits = ctx.repo.retrieve(q, top_k=3, is_filter=use_filter, project=project)
            if not hits and use_filter:
                hits = ctx.repo.retrieve(q, top_k=3, is_filter=False, project=project)
            if not hits:
                print(f"Q empty: {q!r}")
                continue
            d1 = hits[0][0].decision_result
            top1_dists.append(float(hits[0][1]))
            if decision_hit(d1, subs):
                hit1 += 1
            if any(decision_hit(h[0].decision_result, subs) for h in hits[:3]):
                hit3 += 1

            if check_aggregation and qm.get("check_aggregation"):
                agg = await ctx.hiarch.aggregation_memory(q, memory_project=project)
                agg_ok = decision_hit(agg, subs)
                print(f"aggregation_hit={agg_ok} agg_len={len(agg)}")
                if not agg_ok:
                    return 2

        print(f"retrieve_is_filter={use_filter}")
        print(f"Hit@1: {hit1}/{nq}  Hit@3: {hit3}/{nq}")
        if top1_dists:
            print(f"avg_top1_cosine_distance: {sum(top1_dists) / len(top1_dists):.4f}")

        ok = hit1 >= max(1, int(0.5 * nq)) and hit3 >= max(1, int(0.67 * nq))
        if suite == "noise" and not ok:
            print("WARN: below noise targets (Hit@1>=50% Hit@3>=67%)", file=sys.stderr)
            return 2
        if suite == "smoke" and hit1 < 1:
            return 2
        return 0
    finally:
        if not keep_data:
            delete_project_rows(ctx.session, project)
        ctx.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("smoke", "noise", "temporal"), default="smoke")
    parser.add_argument("--noise-limit", type=int, default=None)
    parser.add_argument("--keep-data", action="store_true")
    parser.add_argument("--check-aggregation", action="store_true", help="smoke: 同时校验 HiarchMemoryStore.aggregation_memory")
    args = parser.parse_args()

    lim = args.noise_limit
    if lim is None and os.environ.get("NANOBOT_BENCHMARK_NOISE_LIMIT"):
        lim = int(os.environ["NANOBOT_BENCHMARK_NOISE_LIMIT"])

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

    check_agg = args.check_aggregation or os.environ.get("NANOBOT_ROUTER_CHECK_AGGREGATION") in ("1", "true")
    return asyncio.run(
        _run_async(
            suite=args.suite,
            keep_data=args.keep_data,
            noise_limit=lim,
            check_aggregation=check_agg,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
