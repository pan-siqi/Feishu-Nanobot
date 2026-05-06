#!/usr/bin/env python3
"""在同一进程内依次运行 §5.1–5.3 基准（共享一次 bge 模型加载）。"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main() -> int:
    from test_pipeline import run_efficiency as eff
    from test_pipeline import run_noise_robustness as noise
    from test_pipeline import run_temporal_override as temporal

    saved = sys.argv[:]
    code = 0
    try:
        sys.argv = [noise.__file__]
        if noise.main() != 0:
            code = 1
        sys.argv = [temporal.__file__]
        if temporal.main() != 0:
            code = 1
        sys.argv = [eff.__file__, "--check-report"]
        if eff.main() != 0:
            code = 1
    finally:
        sys.argv = saved
    return code


if __name__ == "__main__":
    raise SystemExit(main())
