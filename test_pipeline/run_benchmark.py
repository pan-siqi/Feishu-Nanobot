#!/usr/bin/env python3
"""
统一测评入口（§5 / 全链路）：子命令驱动 offline、决策 E2E、Router E2E、渠道占位与组合。

示例:
  uv run python test_pipeline/run_benchmark.py offline
  uv run python test_pipeline/run_benchmark.py decision-e2e
  uv run python test_pipeline/run_benchmark.py router-full
  uv run python test_pipeline/run_benchmark.py all-e2e
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_TP = _REPO / "test_pipeline"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _py() -> str:
    return sys.executable


def _run(script: str, extra: list[str] | None = None) -> int:
    cmd = [_py(), str(_TP / script)]
    if extra:
        cmd.extend(extra)
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(_REPO))


def cmd_offline() -> int:
    from test_pipeline import run_efficiency as eff
    from test_pipeline import run_noise_robustness as noise
    from test_pipeline import run_temporal_override as temporal
    from test_pipeline import run_token_estimate as tok

    saved = sys.argv[:]
    code = 0
    try:
        sys.argv = [str(_TP / "run_noise_robustness.py")]
        code = max(code, noise.main())
        sys.argv = [str(_TP / "run_temporal_override.py")]
        code = max(code, temporal.main())
        sys.argv = [str(_TP / "run_efficiency.py"), "--check-report"]
        code = max(code, eff.main())
        sys.argv = [str(_TP / "run_token_estimate.py")]
        code = max(code, tok.main())
    finally:
        sys.argv = saved
    return code


def cmd_decision_e2e() -> int:
    return _run("run_e2e_all.py")


def cmd_router_full() -> int:
    suite = os.environ.get("NANOBOT_ROUTER_SUITE", "smoke")
    extra = ["--suite", suite]
    if os.environ.get("NANOBOT_ROUTER_CHECK_AGGREGATION") in ("1", "true", "yes"):
        extra.append("--check-aggregation")
    return _run("e2e_router_full.py", extra)


def cmd_channel() -> int:
    print(
        "channel: 飞书回调 / Monitor / Cron 等渠道级 E2E 尚未接入本入口。\n"
        "参见 docs/proposal/submission_report_final.md §8.1 与附录。"
    )
    return 5


def cmd_all_e2e() -> int:
    code = cmd_decision_e2e()
    code = max(code, cmd_router_full())
    return code


def cmd_all_offline() -> int:
    return cmd_offline()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_benchmark", description="DecisionMind benchmark 统一入口")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("offline", help="L1 仿真：离线向量 + 效能对账 + Token 估算（无 PG/LLM）").set_defaults(
        func=cmd_offline
    )
    sub.add_parser(
        "decision-e2e",
        help="L2 决策子链：extract→PG→retrieve（Router 卸批外的等价滑窗，见 run_e2e_all）",
    ).set_defaults(func=cmd_decision_e2e)
    sub.add_parser(
        "router-full",
        help="Router 全链路：.history.jsonl→operate_batch（Episodic+Decision），默认 smoke",
    ).set_defaults(func=cmd_router_full)
    sub.add_parser("channel", help="L3 渠道集成占位（当前未实现自动化）").set_defaults(func=cmd_channel)
    sub.add_parser("all-offline", help="同 offline").set_defaults(func=cmd_all_offline)
    sub.add_parser(
        "all-e2e",
        help="decision-e2e 后接 router-full（需 PG+LLM+Neo4j）",
    ).set_defaults(func=cmd_all_e2e)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    parser = build_parser()
    args = parser.parse_args(argv[1:])
    return int(args.func())


if __name__ == "__main__":
    raise SystemExit(main())
