#!/usr/bin/env python3
"""L2 决策子链 E2E：e2e_noise → e2e_temporal → e2e_decision_bench（2 例）。

可选：设置 **`NANOBOT_BENCHMARK_INCLUDE_SEEDS=1`** 时再跑 **`e2e_decision_bench_seeds`**（20 条种子展开，API 调用多，易触发限流）。

与 `run_benchmark decision-e2e` 等价。Router 全链路请用 `run_benchmark router-full` 或 `all-e2e`。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def run(script: str) -> int:
    cmd = [sys.executable, str(_ROOT / script)]
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(_ROOT.parent))


def main() -> int:
    scripts = [
        "e2e_noise.py",
        "e2e_temporal.py",
        "e2e_decision_bench.py",
    ]
    if os.environ.get("NANOBOT_BENCHMARK_INCLUDE_SEEDS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        scripts.append("e2e_decision_bench_seeds.py")

    code = 0
    for script in scripts:
        r = run(script)
        if r != 0:
            code = max(code, r)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
