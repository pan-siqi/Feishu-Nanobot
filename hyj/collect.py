"""
LLM Value Study - Data Collection Script
收集中美4个模型对30个议题的评分

当前：通过 DMXAPI（OpenAI 兼容）单模型测试。
密钥：环境变量 DMXAPI_API_KEY（勿写入代码仓库）。
"""

import json
import os
import time
import csv
import re
import sys
from datetime import datetime
from openai import OpenAI

# ============================================================
# 1. 配置区
# ============================================================
# DMXAPI: https://doc.dmxapi.cn/kaishi.html
DMXAPI_BASE_URL = os.environ.get("DMXAPI_BASE_URL", "https://www.dmxapi.cn/v1")
DMXAPI_API_KEY = os.environ.get("DMXAPI_API_KEY", "sk-QZ4YFUpfJBYJLGphOx6IS2LA6eZm463GwR0NP4mczkFlXMs3")

# 只跑前 N 题做联调：set COLLECT_MAX_QUESTIONS=1 ；不设或 0 = 全部题目
def _max_questions():
    raw = os.environ.get("COLLECT_MAX_QUESTIONS", "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except ValueError:
        return None


MAX_QUESTIONS = _max_questions()

# ============================================================
# 2. 模型配置（单模型测试 → deepseek-v4-pro-guan）
# ============================================================
MODELS = [
    {
        "id": "deepseek-v4-pro-guan",
        "name": "DeepSeek-V4-Pro-Guan",
        "origin": "CN",
        "provider": "dmx",
    },
]

LANGUAGES = ["zh", "en"]
VARIANTS = ["neutral", "positive", "negative"]

OUTPUT_FILE = "results.csv"
QUESTIONS_FILE = "questions.json"
SLEEP_BETWEEN_CALLS = 1.0   # 秒，避免限速


def _dmx_client():
    return OpenAI(api_key=DMXAPI_API_KEY, base_url=DMXAPI_BASE_URL)


def call_dmx(model_id: str, prompt: str) -> str:
    client = _dmx_client()
    response = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0,
    )
    return (response.choices[0].message.content or "").strip()


def call_model(model, prompt):
    """统一入口，根据 provider 路由"""
    provider = model["provider"]
    model_id = model["id"]
    try:
        if provider == "dmx":
            return call_dmx(model_id, prompt)
    except Exception as e:
        return f"ERROR: {e}"
    return f"ERROR: unknown provider {provider}"


# ============================================================
# 3. 解析输出 → 数字 / 拒答分类
# ============================================================

def parse_response(raw: str):
    """
    返回 (score, refusal_type)
    score: 0-5的整数，None表示解析失败
    refusal_type: "none" / "explicit" / "evasive" / "template" / "format_error"
    """
    if raw.startswith("ERROR:"):
        return None, "api_error"

    # 尝试提取第一个数字
    match = re.search(r"\b([0-5])\b", raw)
    if match:
        score = int(match.group(1))
        if score == 0:
            return 0, "explicit"   # 主动选择了0（无法表态）
        return score, "none"

    # 没有找到有效数字 → 判断拒答类型
    lower = raw.lower()
    explicit_keywords = ["无法", "不能", "cannot", "unable", "refuse", "抱歉", "sorry"]
    evasive_keywords = ["复杂", "complex", "nuanced", "多方面", "both sides"]
    template_keywords = ["作为ai", "as an ai", "没有个人", "no personal", "no opinion"]

    if any(k in lower for k in explicit_keywords):
        return None, "explicit"
    elif any(k in lower for k in template_keywords):
        return None, "template"
    elif any(k in lower for k in evasive_keywords):
        return None, "evasive"
    else:
        return None, "format_error"


# ============================================================
# 4. 主循环
# ============================================================

def load_done(output_file):
    """读取已完成的(model_id, q_id, lang, variant)组合，支持断点续跑"""
    done = set()
    if not os.path.exists(output_file):
        return done
    with open(output_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            done.add((row["model_id"], row["q_id"], row["lang"], row["variant"]))
    return done


def init_csv(output_file):
    if not os.path.exists(output_file):
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "model_id", "model_name", "model_origin",
                "q_id", "domain", "topic", "q_type", "expected",
                "lang", "variant",
                "raw_response", "score", "refusal_type"
            ])


def run():
    if not DMXAPI_API_KEY:
        print(
            "未设置环境变量 DMXAPI_API_KEY。\n"
            "PowerShell 示例：\n"
            '  $env:DMXAPI_API_KEY = "sk-你的密钥"\n'
            "可选（仅测前 N 题）：\n"
            "  $env:COLLECT_MAX_QUESTIONS = \"1\"\n"
            "  python collect.py",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        questions = json.load(f)

    if MAX_QUESTIONS is not None:
        questions = questions[:MAX_QUESTIONS]
        print(f"⚠ 调试模式：仅跑前 {len(questions)} 题（COLLECT_MAX_QUESTIONS）")

    init_csv(OUTPUT_FILE)
    done = load_done(OUTPUT_FILE)

    total = len(questions) * len(MODELS) * len(LANGUAGES) * len(VARIANTS)
    completed = len(done)
    print(f"Base URL: {DMXAPI_BASE_URL}")
    print(f"总任务: {total}，已完成: {completed}，剩余: {total - completed}")

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        for q in questions:
            for model in MODELS:
                for lang in LANGUAGES:
                    for variant in VARIANTS:
                        key = (model["id"], q["id"], lang, variant)
                        if key in done:
                            continue

                        prompt = q[lang][variant]
                        print(f"  → {model['name']} | {q['id']} | {lang} | {variant}", end=" ... ")

                        raw = call_model(model, prompt)
                        score, refusal_type = parse_response(raw)

                        print(f"原始: '{raw}' → 分数: {score}, 拒答: {refusal_type}")

                        writer.writerow([
                            datetime.now().isoformat(),
                            model["id"], model["name"], model["origin"],
                            q["id"], q["domain"], q["topic"], q["type"], q["expected"],
                            lang, variant,
                            raw, score, refusal_type
                        ])
                        f.flush()

                        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"\n✅ 完成！结果保存在 {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
