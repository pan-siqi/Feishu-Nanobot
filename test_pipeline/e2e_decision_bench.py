#!/usr/bin/env python3
"""对 decision_bench_e2e_cases.json 逐条跑 extract + retrieve（需 PG + LLM）。"""

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


async def run_all_cases(*, keep_data: bool) -> int:
    path = report_fixture_path("decision_bench_e2e_cases.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"]
    code = 0
    for case in cases:
        pid = case["project"]
        ctx = make_benchmark_context(
            pid, max_score=float(os.environ.get("NANOBOT_BENCHMARK_MAX_SCORE", "0.5"))
        )
        try:
            await batched_decision_extract(ctx.store, list(case["dialogue"]), pid, window_size=50, overlap=5)
            ctx.repo.build_embed()
            q = case["query"]
            subs = list(case["hit_substrings"])
            hits = ctx.repo.retrieve(q, top_k=3, is_filter=True, project=pid)
            if not hits:
                hits = ctx.repo.retrieve(q, top_k=3, is_filter=False, project=pid)
            if not hits:
                print(f"FAIL {case['id']}: no hits", file=sys.stderr)
                code = max(code, 2)
                continue
            top1 = hits[0][0].decision_result
            ok = decision_hit(top1, subs)
            print(f"case {case['id']}: hit@1={ok} top1[:100]={top1[:100]!r}")
            if not ok:
                code = max(code, 2)
        finally:
            if not keep_data:
                delete_project_rows(ctx.session, pid)
            ctx.close()
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
    return asyncio.run(run_all_cases(keep_data=args.keep_data))


if __name__ == "__main__":
    raise SystemExit(main())
