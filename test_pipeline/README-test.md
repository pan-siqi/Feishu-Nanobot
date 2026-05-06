# test_pipeline 使用说明

本目录实现提交报告 **§5 Benchmark** 的 **三层测评** 与 **统一入口**（`run_benchmark.py`）：

| 分层 | 入口子命令 | 内容 |
|------|------------|------|
| **L1 离线** | `offline` / `all-offline` | 无 PG、无 LLM：向量几何仿真、效能对账、Token 估算 |
| **L2 决策 E2E** | `decision-e2e` | 真实 `DecisionMemoryStore.extract` → PG → `retrieve`（`run_e2e_all`：抗干扰、时序、DecisionBench 子集） |
| **L2+ Router 全链** | `router-full` | 真实 `Router.operate_batch`：`.history.jsonl` 切窗 → **Episodic（LightRAG+Neo4j）+ Decision** |
| **L3 渠道** | `channel` | 占位（飞书回调 / Monitor / Cron 未接自动化，见主报告 §8.1） |

**工作目录**：以下命令均在仓库根目录 `Feishu-Nanobot/` 下执行（`uv run python test_pipeline/...`）。

---

## 1. 目录与数据

### 1.1 报告 fixtures（`fixtures/report/`）

| 路径 | 说明 |
|------|------|
| `fixtures/report/noise_robustness/fixture.json` | §5.1 抗干扰：信号、噪声、6 条查询、金标准 `golden_decision` |
| `fixtures/report/temporal_override/fixture.json` | §5.2 时序覆写：批次 A/B、合并后期望字段 |
| `fixtures/report/efficiency/tasks.json` | §5.3 效能：无/有记忆文案与步数、`report_reference_totals` |
| `fixtures/report/decision_bench_50_seeds.json` | §5.5：20 条种子（扩展用） |
| `fixtures/report/decision_bench_e2e_cases.json` | DecisionBench 自动子集（鉴权、周报等） |

历史路径 `test_pipeline/data/` 已迁移至此；`helpers.load_dataset_json` 仍兼容遗留 `data/`（若仍存在）。

### 1.2 场景 fixtures（`fixtures/scenarios/`）

| 路径 | 说明 |
|------|------|
| `fixtures/scenarios/smoke_router.json` | Router 全链路 **烟测**（消息少；默认 `e2e_router_full --suite smoke`） |

### 1.3 代码

| 文件 | 说明 |
|------|------|
| `run_benchmark.py` | **主入口**（子命令见下节） |
| `runtime.py` | PG、Provider、**`make_router_pipeline_context`（Router+Episodic+Decision+Hiarch）**、`batched_decision_extract` |
| `helpers.py` | `fixtures/report` 加载、`REPORT_FIXTURES_DIR` / `DATA_DIR` |

---

## 2. 统一入口：`run_benchmark.py`

```bash
cd /path/to/Feishu-Nanobot

# L1 离线全套（推荐日常 / CI 无密钥）
uv run python test_pipeline/run_benchmark.py offline

# L2 仅决策子链 E2E（PG + LLM，不含 Router）
uv run python test_pipeline/run_benchmark.py decision-e2e

# Router 全链路（PG + LLM + Neo4j；默认 smoke 场景）
uv run python test_pipeline/run_benchmark.py router-full

# L2 决策 E2E + Router smoke（完整集成评测）
uv run python test_pipeline/run_benchmark.py all-e2e

# L3 占位
uv run python test_pipeline/run_benchmark.py channel   # 退出码 5
```

### 2.1 兼容封装：`run_all.py`

```bash
uv run python test_pipeline/run_all.py                  # = run_benchmark offline
uv run python test_pipeline/run_all.py --with-e2e      # = run_benchmark all-e2e
```

### 2.2 Router 套件与聚合

| 环境变量 | 含义 |
|----------|------|
| `NANOBOT_ROUTER_SUITE` | `smoke`（默认）/ `noise` / `temporal`：传给 `e2e_router_full --suite` |
| `NANOBOT_ROUTER_CHECK_AGGREGATION=1` | 为 `router-full` 子进程附加 `--check-aggregation`（校验 `HiarchMemoryStore.aggregation_memory`） |
| `NANOBOT_MEMORY_ROUTE_ALL=1` | `e2e_router_full` 内 **默认 setdefault**，使决策与情景层均参与聚合；勿覆盖除非刻意测 QueryRouter 默认行为 |

### 2.3 与 `run_e2e_all.py` 的关系

- `decision-e2e` 与 `uv run python test_pipeline/run_e2e_all.py` **等价**（依次 `e2e_noise` → `e2e_temporal` → `e2e_decision_bench`）。  
- **完整「决策 + Router」** 请用 **`all-e2e`**（= `decision-e2e` 再跑 **`e2e_router_full`**，默认 **smoke**）。

---

## 3. 离线分项（L1）

```bash
uv run python test_pipeline/run_noise_robustness.py
uv run python test_pipeline/run_temporal_override.py
uv run python test_pipeline/run_efficiency.py --check-report
uv run python test_pipeline/run_token_estimate.py
```

---

## 4. E2E 分项

### 4.1 决策子链（与报告 §5.1 / §5.2 Hit 指标对齐）

```bash
uv run python test_pipeline/e2e_noise.py
uv run python test_pipeline/e2e_temporal.py
uv run python test_pipeline/e2e_decision_bench.py
```

常用变量：见下文 §6；`e2e_noise` 支持 `--single-extract`、`--window-size` / `--overlap`、`NANOBOT_BENCHMARK_MAX_SCORE` 等。

### 4.2 Router 全链路（报告所述「经 Router 卸批」）

```bash
# 默认烟测（最少消息）
uv run python test_pipeline/e2e_router_full.py

# 报告级噪声集（成本高）
uv run python test_pipeline/e2e_router_full.py --suite noise

# 时序覆写两批对话
uv run python test_pipeline/e2e_router_full.py --suite temporal
```

**依赖**：PostgreSQL（pgvector）、**Neo4j**（`NEO4J_URI`、`NEO4J_USERNAME`、`NEO4J_PASSWORD`）、LLM、本地 **bge**。LightRAG 使用 Neo4j 图存储；初始化失败时退出码 **6**。

---

## 5. 环境与模型

### 5.1 PostgreSQL

与 `nanobot/agent/hiarch_memory/database/base.py` 一致：`NANOBOT_PG_*`。首次 E2E 会通过 `runtime.init_decision_schema` 建表并补列。

### 5.2 Neo4j（仅 `router-full` / `e2e_router_full`）

LightRAG `Neo4JStorage` 常用变量（参见 LightRAG 文档）：

- `NEO4J_URI`（如 `neo4j://localhost:7687`）
- `NEO4J_USERNAME` / `NEO4J_PASSWORD`
- 可选：`NEO4J_DATABASE`、`NEO4J_WORKSPACE`

### 5.3 LLM（OpenAI 兼容）

- `OPENAI_API_KEY` 或 `NANOBOT_BENCHMARK_OPENAI_API_KEY` 或 `LLM_BINDING_API_KEY`
- `NANOBOT_BENCHMARK_OPENAI_BASE` / `OPENAI_API_BASE` / `OPENAI_BASE_URL` / `LLM_BINDING_HOST`
- `NANOBOT_BENCHMARK_MODEL`（默认 `gpt-4o-mini`，或与 `.nanobot/config.json` 里 `agents.defaults.model` 一致）

若上述环境变量未设置，测评会从仓库根目录 **`.nanobot/config.json`** 读取 **`providers.custom`**（`apiKey`、`apiBase`）及 **`agents.defaults.model`**，与本地运行 `fsbot` 时的自定义网关一致。

Episodic 内 LightRAG 的 LLM 适配层可能与 Volcengine 配置耦合；若 Router 全链路与决策 E2E 行为不一致，请核对线上 **同一 base_url/model**。

### 5.4 嵌入模型

仓库根目录 **`model/bge-small-zh-v1.5/`**，否则尝试 HuggingFace **`BAAI/bge-small-zh-v1.5`**。

---

## 6. 退出码约定（E2E / router）

| 退出码 | 含义 |
|--------|------|
| `0` | 成功或通过阈值 |
| `2` | 指标未达标（Hit、覆写、聚合等） |
| `3` | 数据库不可用 |
| `4` | LLM/API Key 配置错误 |
| `5` | `channel` 子命令占位 |
| `6` | LightRAG / Neo4j 初始化失败 |

---

## 7. 扩展数据集

- **报告三项**：编辑 `fixtures/report/` 下对应 JSON；效能修改后请同步 `report_reference_totals` 或去掉 `--check-report`。  
- **Router 烟测**：编辑 `fixtures/scenarios/smoke_router.json`。  
- **DecisionBench 小题**：编辑 `fixtures/report/decision_bench_e2e_cases.json`。  
- **Router 跑报告级噪声/时序**：使用 `e2e_router_full.py --suite noise|temporal`（与 `fixtures/report` 中 fixture 一致）。

---

## 8. 分层与「整条链路」说明

- **`decision-e2e`**：只验证 **决策记忆**（与 §5.1/§5.2 **表格指标**直接对齐）；不启动 Neo4j。  
- **`router-full`**：验证 **`Router.operate_batch`** 双通道写入 + 检索；默认 **smoke** 控制成本。  
- **`all-e2e`**：先跑决策三项再跑 Router smoke，覆盖 **决策质量 + 真 Router 路径**。  
- **飞书 / Cron**：不在本目录自动化；见 `submission_report_final.md` §8.1。

---

*文档与 `test_pipeline` 脚本同步；首选入口为 **`run_benchmark.py`**。*
