#!/usr/bin/env python3
"""兼容入口：等价于 `run_benchmark offline`，或 `--with-e2e` → `run_benchmark all-e2e`。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    argv = sys.argv[1:]
    if "--with-e2e" in argv:
        argv = [a for a in argv if a != "--with-e2e"]
        sys.argv = [sys.argv[0], "all-e2e", *argv]
    else:
        sys.argv = [sys.argv[0], "offline", *argv]
    from test_pipeline.run_benchmark import main as bench_main

    return bench_main()


if __name__ == "__main__":
    raise SystemExit(main())
