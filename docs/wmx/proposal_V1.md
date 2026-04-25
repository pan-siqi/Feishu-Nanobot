# 企业级记忆引擎：方向 B（决策记忆）+ 方向 D（遗忘曲线）落地方案

> 作者：产品架构师 / 三人团队  
> 载体：基于本仓库 `Feishu-Nanobot`（HKUDS/nanobot 二次开发）  
> 周期：9 个自然日（3 个 Sprint × 3 天），每 3 天每人登记一次"学习 + 产出"

---

## 0. 一句话项目定义

> **Feishu-Nanobot · DecisionMind**：一个跑在飞书 + CLI 双端的"决策记忆引擎"。它会自动从群聊 / 文档 / CLI 操作中**抽取决策（Decision-Reason-Conclusion）**，按**艾宾浩斯遗忘曲线**衰减权重，在新讨论触及旧话题时**主动推送历史决策卡片**，并在关键决策即将被团队遗忘时**广播复习提醒**。

赛题三大挑战的对应：

| 挑战 | 我们的回答 |
|---|---|
| ① 重新定义记忆 | 企业记忆 ≠ 聊天日志，而是 **"带时间戳的结构化决策图谱（Decision Graph）"**：节点 = 决策 / 理由 / 反对意见 / 结论，边 = supersede / supports / conflicts / depends-on。CLI 高频命令、飞书文档变更只是**触发器**，真正沉淀的是"为什么这样做"。 |
| ② 构建记忆引擎 | 在 `nanobot/agent/hiarch_memory/` 已有的 STM + Episodic(LightRAG) 之上，新增 **Decision Layer**（结构化 SQLite + 图）+ **Forgetting Scheduler**（cron 周期衰减），通过 `nanobot/skills/memory/` 暴露 `recall / inject / review`，CLI 与飞书共享同一存储。 |
| ③ 证明价值 | 自建 50 条**决策评测集**（DecisionBench），指标：决策召回率、重复争论拦截率、复习提醒命中率、Token 节省率，对照实验 vs 朴素 RAG。 |

---

## 1. 现状盘点（基于本仓库实际代码）

| 已有能力 | 位置 | 复用方式 |
|---|---|---|
| 飞书长连接 + 流式卡片 | `nanobot/channels/feishu.py` | 直接复用，新增"决策卡片"模板 |
| 短期记忆 / 滑动窗口 | `nanobot/agent/hiarch_memory/shorterm.py` | 作为决策抽取的输入流 |
| 情景记忆 + LightRAG + Neo4j | `nanobot/agent/hiarch_memory/episodic.py` | 复用图存储能力，扩展决策子图 |
| 记忆聚合入口 | `nanobot/agent/hiarch_memory/memory.py::aggregation_memory` | 新增 Router：意图分发到 decision / episodic |
| Skill 注册框架 | `nanobot/skills/memory/SKILL.md` | 新增 `decision` skill，暴露工具给 LLM |
| CLI 框架 | `nanobot/cli/commands.py` + `nanobot/command/` | 新增 `claw memory recall/inject/review` |
| 定时任务 | `nanobot/cron/` | 跑遗忘衰减 + 复习扫描 |
| Provider 结构化输出 | `episodic.py::chat_scheme` | 直接套用 `Decision` Pydantic schema |

**结论**：底座基本齐备，方向 B/D 不需要大改架构，**新增 1 个层（Decision Layer）+ 2 个 skill + 1 个 cron 即可**。

---

## 2. 重新架构：在现有 Hiarch Memory 上加 "Decision Layer"

```
┌─────────────────────────────────────────────────────────────┐
│   Channel Layer：feishu.py  /  cli/commands.py              │
└────────────┬────────────────────────────────┬───────────────┘
             ↓ 入站消息                        ↑ 主动推送 / 卡片
┌─────────────────────────────────────────────────────────────┐
│   Agent Loop (agent/loop.py)                                │
│        ↓ context.py::_build_system_prompt                   │
│   HiarchMemoryStore.aggregation_memory(msg)                 │
│   ┌──────────────┐  Router (意图分类: 是否触及历史决策?)     │
│   │   Router     │ ───→ DecisionStore.recall(topic)         │
│   └──────┬───────┘ ───→ EpisodicStore.retrieve(msg)  (旧)   │
│          ↓                                                  │
│   ┌──────────────────────────────────────────────────┐      │
│   │  ★ NEW: DecisionMemoryStore                      │      │
│   │  - extract():  LLM + Pydantic → Decision         │      │
│   │  - store():    SQLite(决策事实) + Neo4j(决策图)   │      │
│   │  - recall():   语义+图混合检索 + 时序权重          │      │
│   │  - decay():    Ebbinghaus  R = e^(-t/S)          │      │
│   │  - supersede(): 新决策覆盖旧决策（版本链）         │      │
│   └──────────────────────────────────────────────────┘      │
│          ↑ 写                       ↓ 读                    │
│   ShortTerm  Episodic(LightRAG)  Working  Semantic          │
└─────────────────────────────────────────────────────────────┘
             ↑ cron/decision_review.py
       每小时扫描 → 命中遗忘阈值 → 飞书群"复习卡片"
```

### 2.1 决策数据结构（核心 Schema）

```python
# nanobot/agent/hiarch_memory/decision.py  (NEW)
class Decision(BaseModel):
    id: str
    project: str                # 关联项目/群聊 id
    topic: str                  # 归一化主题，e.g. "auth_strategy"
    statement: str              # 结论，一句话
    reasons: list[str]          # 支持理由
    objections: list[str]       # 反对意见 / 风险
    alternatives: list[str]     # 被放弃的方案 (e.g. "方案A")
    decided_at: int             # 决策时间戳
    deadline: int | None        # 关联截止日（方向 B 关键）
    participants: list[str]     # open_id 列表
    source: Literal["chat","doc","cli","manual"]
    source_ref: str             # message_id / doc_token
    importance: float           # 0~1
    # —— 方向 D：遗忘曲线字段 ——
    last_reviewed_at: int
    review_count: int
    strength: float             # 记忆强度 S，每次 review 增大
    supersedes: str | None      # 旧决策 id（版本链）
    status: Literal["active","superseded","expired"]
```

### 2.2 关键算法

- **抽取**：复用 `episodic.py` 的 `chat_scheme`，提示词改写为"识别讨论中的 decision/objection/conclusion 三元组"。增量触发：每次 STM rebuild 时执行。
- **遗忘曲线**：`R(t) = exp(-Δt / S)`，S 初始 = 1 day × importance × 5；每次 recall 命中 → `S *= 1.8`（间隔重复）。当 R < 0.4 且 importance > 0.6 → 进入复习队列。
- **主动推送触发**：新消息进入 → embed → 与 active 决策做 cosine sim，>0.78 且 topic 匹配则在卡片中渲染 "📌 历史决策回顾"。
- **Supersede**：抽取到与旧决策 topic 相同但 statement 冲突 → LLM 二次裁决 → 旧决策 status=superseded，新决策 supersedes=old.id。

---

## 3. 评测设计（挑战三）：DecisionBench-50

| 指标 | 定义 | 目标 |
|---|---|---|
| Decision-Recall@5 | 给定新问题，是否在 top-5 召回正确历史决策 | ≥ 0.85 |
| Repeat-Debate-Block | 模拟"重提旧争论"，系统主动拦截率 | ≥ 0.75 |
| Forget-Alert-Precision | 复习提醒中"用户认可有用"的比例 | ≥ 0.70 |
| Token-Saved | 对照朴素全量上下文，平均 prompt token 节省 | ≥ 40% |
| Latency | 端到端推送延时（消息→卡片） | ≤ 2.5s |

测试集构造：基于公开飞书群聊脱敏样本 + 手工编写 50 个决策场景（含 supersede / 跨周复述 / 干扰项），存于 `docs/bench/decisionbench.jsonl`。

---

## 4. 三人团队 9 天作战计划

> 角色定义（按现有代码栈匹配）：
> - **A · Memory Core**（懂 Python/RAG/图）：决策抽取、存储、衰减算法
> - **B · Channel & UX**（懂飞书 SDK/卡片/CLI）：飞书卡片、CLI 命令、主动推送
> - **C · Eval & Product**（懂指标/数据/Prompt）：DecisionBench、Prompt 工程、Demo 脚本

### Sprint 1（Day 1–3）：打地基 — "能抽出决策 + 能存进去"

| 成员 | 任务 | 交付物 |
|---|---|---|
| A | 新建 `nanobot/agent/hiarch_memory/decision.py`，定义 `Decision` schema + `DecisionMemoryStore`（SQLite 落地 + 复用 LightRAG 图存储），实现 `extract() / store()` | 单测：给定 1 段对话，能产出结构化决策记录 |
| B | 飞书侧：在 `channels/feishu.py` 增加 "决策卡片"模板（标题/理由/反对/结论/时间）；CLI 侧：`nanobot/cli/commands.py` 新增 `claw memory inject --topic=...` | `claw memory inject` 可写入 1 条决策；飞书能渲染卡片 |
| C | 编写 `docs/bench/decisionbench.jsonl` 前 20 条样例 + 抽取 Prompt v1（`templates/custom/decision_extract.md`） | 20 条标注数据 + Prompt 文件；跑通 A 的抽取得到 baseline 准确率 |

**Day 3 个人复盘记录** → 写入 `docs/logs/sprint1_<name>.md`，包含：① 学到了什么（如 LightRAG 图 schema、飞书 CardKit）② 完成了什么 ③ 阻塞点。

### Sprint 2（Day 4–6）：见智能 — "能召回 + 能遗忘 + 能 supersede"

| 成员 | 任务 | 交付物 |
|---|---|---|
| A | 实现 `recall()` 混合检索（语义+图+时序）、`decay()` 遗忘曲线、`supersede()` 版本链；接入 `memory.py::aggregation_memory` 的 Router | `aggregation_memory` 在触及旧话题时返回决策摘要而非全文 |
| B | `nanobot/cron/` 新增 `decision_review.py`：每小时扫描遗忘阈值 → 调 feishu 推送复习卡；CLI `claw memory recall/review` 完工；卡片支持"确认/废弃/更新"按钮回写 | 群聊里能自动收到复习提醒；点按钮能更新决策状态 |
| C | DecisionBench 扩展到 50 条；搭建评测脚本 `scripts/eval_decisionbench.py`；产出 Sprint1 baseline vs Sprint2 对比报告 | 评测报告 v1，至少跑出 Recall@5 数字 |

**Day 6 个人复盘** → `docs/logs/sprint2_<name>.md`。

### Sprint 3（Day 7–9）：出 Demo — "讲故事 + 出指标 + 防翻车"

| 成员 | 任务 | 交付物 |
|---|---|---|
| A | 性能优化：embedding 缓存、SQLite 索引、并发安全；修复评测中暴露的 bad case；冻结 API | 端到端延时 ≤ 2.5s；通过 50 条 bench |
| B | 录制 3 分钟 Demo（飞书群"重启旧争论 → 卡片拦截"+"截止日临近 → 主动提醒"+"CLI 双端互通"）；写部署文档 `docs/deploy.md` | Demo 视频 + 一键启动脚本 `run_demo.sh` |
| C | 完成最终评测报告（含对照实验：朴素 RAG vs Decision Layer），整理 PPT 与答辩 Q&A，更新主 `README.md` 的"开发更新日志" | `docs/report.md` + `docs/slides.pdf` |

**Day 9 个人复盘** → `docs/logs/sprint3_<name>.md` + 团队总结 `docs/logs/retro.md`。

### 三次打卡的统一模板（每人每 3 天填一次）

```markdown
# Sprint <N> · <Name> · <YYYY-MM-DD>
## 学习 (Learn)
- 知识点 1：...
- 知识点 2：...
## 完成 (Done)
- [x] 任务 / PR 链接
- [x] ...
## 数据 / 指标
- (e.g. Recall@5 = 0.62)
## 阻塞 & 下一步
- 阻塞：...
- 明日计划：...
```

---

## 5. 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| LLM 抽决策幻觉 / 漏抽 | 高 | Prompt 双轮 self-check + DecisionBench 守门 |
| Neo4j 部署门槛 | 中 | 默认走 SQLite + LightRAG 内置 KV 图，Neo4j 列为可选 |
| 飞书 `cardkit:card:write` 权限申请慢 | 中 | 同步走普通卡片回退（仓库已支持 `streaming:false`） |
| 9 天时间紧 | 高 | Day 6 卡点：若评测未达 0.7，砍掉 supersede 的 LLM 二次裁决，改为规则版 |
| 三人协作冲突 | 中 | A 负责 `hiarch_memory/`、B 负责 `channels/+cli/+cron/`、C 负责 `docs/+scripts/`，物理隔离最小化冲突 |

---

## 6. 立即可执行的下一步（Day 1 上午）

1. **A**：`git checkout -b feat/decision-layer`，建空文件 `nanobot/agent/hiarch_memory/decision.py` 与 `templates/custom/decision_extract.md`。
2. **B**：调研现有 `channels/feishu.py` 中 CardKit 用法（搜索 `interactive` / `card`），起 `feat/decision-card` 分支，先做静态卡片。
3. **C**：建 `docs/bench/decisionbench.jsonl` 与 `docs/logs/`，把第一批 5 条样本写出来给 A 调 Prompt。
4. 全员：在飞书建 "DecisionMind 研发群"，把 bot 拉进去做实时联调环境。

> 一旦此文档通过评审，三人即按 §4 表格各自 fork 任务，每 3 天回到本仓库 `docs/logs/` 提交打卡 markdown，形成可追溯的过程证据。
