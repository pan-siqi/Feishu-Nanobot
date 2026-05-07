#!/usr/bin/env python3
"""对 decision_bench_seed_cases.json 逐条跑 extract + retrieve（20 条种子展开，需 PG + LLM）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
os.chdir(_REPO)

from test_pipeline.helpers import report_fixture_path
from test_pipeline.runtime import (
    batched_decision_extract,
    benchmark_openai_provider,
    connect_session,
    decision_hit,
    delete_project_rows,
    init_decision_schema,
    make_benchmark_context,
)


async def _extract_with_retries(
    store,
    dialogue: list[str],
    pid: str,
    *,
    retries: int,
    backoff_sec: float,
) -> None:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            await batched_decision_extract(
                store, list(dialogue), pid, window_size=50, overlap=5
            )
            return
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < retries:
                await asyncio.sleep(backoff_sec * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("extract retries exhausted")


async def run_seed_cases(*, keep_data: bool) -> int:
    path = report_fixture_path("decision_bench_seed_cases.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    code = 0
    max_score = float(os.environ.get("NANOBOT_BENCHMARK_MAX_SCORE", "0.5"))

    retries = max(1, int(os.environ.get("NANOBOT_BENCHMARK_SEED_EXTRACT_RETRIES", "5")))
    backoff = float(os.environ.get("NANOBOT_BENCHMARK_SEED_EXTRACT_BACKOFF_SEC", "2.0"))
    gap = float(os.environ.get("NANOBOT_BENCHMARK_INTER_CASE_SLEEP_SEC", "2.0"))

    for case in cases:
        cid = case["id"]
        if case.get("skip"):
            print(f"SKIP {cid}: {case.get('skip_reason', '')}".strip())
            continue

        pid = case["project"]
        ctx = make_benchmark_context(pid, max_score=max_score)
        try:
            try:
                await _extract_with_retries(
                    ctx.store,
                    list(case["dialogue"]),
                    pid,
                    retries=retries,
                    backoff_sec=backoff,
                )
            except Exception as exc:
                print(f"FAIL {cid}: extract/pipeline {exc}", file=sys.stderr)
                code = max(code, 2)
                continue

            ctx.repo.build_embed()
            q = case["query"]

            if case.get("expect_empty_retrieval"):
                hits = ctx.repo.retrieve(q, top_k=3, is_filter=True, project=pid)
                if not hits:
                    hits = ctx.repo.retrieve(q, top_k=3, is_filter=False, project=pid)
                if hits:
                    top1 = hits[0][0].decision_result
                    print(
                        f"FAIL {cid}: expect_empty_retrieval but got top1[:80]={top1[:80]!r}",
                        file=sys.stderr,
                    )
                    code = max(code, 2)
                else:
                    print(f"case {cid}: expect_empty_retrieval ok (no hits)")
                continue

            subs = list(case.get("hit_substrings") or [])
            hits = ctx.repo.retrieve(q, top_k=3, is_filter=True, project=pid)
            if not hits:
                hits = ctx.repo.retrieve(q, top_k=3, is_filter=False, project=pid)
            if not hits:
                print(f"FAIL {cid}: no hits", file=sys.stderr)
                code = max(code, 2)
                continue
            top1 = hits[0][0].decision_result
            ok = decision_hit(top1, subs)
            print(f"case {cid}: hit@1={ok} top1[:100]={top1[:100]!r}")
            if not ok:
                code = max(code, 2)
        finally:
            if not keep_data:
                delete_project_rows(ctx.session, pid)
            ctx.close()
        if gap > 0:
            await asyncio.sleep(gap)
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-data", action="store_true")
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
    return asyncio.run(run_seed_cases(keep_data=args.keep_data))


if __name__ == "__main__":
    raise SystemExit(main())
