#!/usr/bin/env python3
"""
效能指标验证（submission_report_final.md §5.3）

根据 fixtures/report/efficiency/tasks.json 复算字符数、步骤数及汇总表；可选与报告参考总值对账。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from test_pipeline.helpers import DATA_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description="Efficiency metrics benchmark (§5.3)")
    parser.add_argument("--check-report", action="store_true", help="与 tasks.json 内 report_reference_totals 严格对账")
    args = parser.parse_args()

    path = DATA_DIR / "efficiency" / "tasks.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    tasks = data["tasks"]
    rows = []
    total_wo = total_w = 0
    steps_wo = steps_w = 0
    char_rates: list[float] = []
    step_rates: list[float] = []

    for t in tasks:
        wo = t["without_memory"]["user_text"]
        w = t["with_memory"]["user_text"]
        cwo, cw = len(wo), len(w)
        swo, sw = t["without_memory"]["steps"], t["with_memory"]["steps"]
        total_wo += cwo
        total_w += cw
        steps_wo += swo
        steps_w += sw
        char_red = (cwo - cw) / cwo * 100 if cwo else 0.0
        step_red = (swo - sw) / swo * 100 if swo else 0.0
        char_rates.append(char_red)
        step_rates.append(step_red)
        rows.append((t["title"], cwo, cw, char_red, swo, sw, step_red))

    print("=== Efficiency metrics (§5.3) ===")
    for title, cwo, cw, cr, swo, sw, sr in rows:
        print(f"- {title}: chars {cwo}→{cw} ({cr:.1f}% ↓); steps {swo}→{sw} ({sr:.1f}% ↓)")

    avg_char = sum(char_rates) / len(char_rates)
    avg_step = sum(step_rates) / len(step_rates)
    print()
    print(f"5-task total chars: {total_wo} → {total_w} (↓{100.0 * (total_wo - total_w) / total_wo:.1f}%)")
    print(f"5-task total steps: {steps_wo} → {steps_w} (↓{100.0 * (steps_wo - steps_w) / steps_wo:.1f}%)")
    print(f"avg char reduction rate: {avg_char:.1f}%")
    print(f"avg step reduction rate: {avg_step:.1f}%")

    ref = data.get("report_reference_totals", {})
    if ref:
        ts = sum(t["time_saved_seconds"] for t in tasks)
        print(f"sum(time_saved_seconds) from tasks: {ts}s")
    if args.check_report and ref:
        assert total_wo == ref["chars_without_memory"], "char total mismatch"
        assert total_w == ref["chars_with_memory"], "char with mismatch"
        assert steps_wo == ref["steps_without_memory"], "steps mismatch"
        assert steps_w == ref["steps_with_memory"], "steps with mismatch"
        assert sum(t["time_saved_seconds"] for t in tasks) == ref["total_time_saved_seconds"], "time sum mismatch"
        print("report_reference_totals: OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
