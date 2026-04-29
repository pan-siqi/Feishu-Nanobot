# 企业级记忆引擎：方向 B（决策记忆）+ 方向 D（遗忘曲线）落地方案

> 作者：产品架构师 / 三人团队  
> 载体：基于本仓库 `Feishu-Nanobot`（HKUDS/nanobot 二次开发）  
> 周期：9 个自然日（3 个 Sprint × 3 天），每 3 天每人登记一次"学习 + 产出"

---

## 0. 电梯演讲（30 秒讲明白我们在做什么）

> 想象一下：你们团队上周五在飞书群里激烈讨论了 2 小时，最后定了"用方案 B 不用方案 A"。  
> 一周后，新同事在群里又问："咱们 API 鉴权到底用 JWT 还是 Session？"——所有人沉默 3 分钟，没人记得清当时为什么否了 Session。  
> 又过了两周，方案 B 里那个"必须在 5 号前上线"的 deadline，全员忘得一干二净。

**我们要造的就是一个"团队的海马体"——它叫 DecisionMind**：

- 它躲在飞书群和你的命令行（CLI）里，**默默听**你们讨论；
- 听到关键决策（"我们决定 X，因为 Y，否决了 Z"），它**自动记成结构化卡片**；
- 下次有人重提旧话题，它**主动弹出 1 张卡片**："📌 上周五已决定：用 B，否了 A，理由是 …"；
- 关键事项快被遗忘时（用艾宾浩斯遗忘曲线算），它**主动在群里 @ 大家复习**；
- 决策被更新时，它**自动把旧版本归档**，不会让你看到过期信息。

**一句话**：让大模型不再"金鱼记忆"，让企业知识从"群聊河里的水"变成"可检索的冰块"。

---

## 0.1 一句话项目定义（给评委的标准答案）

> **Feishu-Nanobot · DecisionMind**：一个跑在飞书 + CLI 双端的"决策记忆引擎"。它会自动从群聊 / 文档 / CLI 操作中**抽取决策（Decision-Reason-Conclusion）**，按**艾宾浩斯遗忘曲线**衰减权重，在新讨论触及旧话题时**主动推送历史决策卡片**，并在关键决策即将被团队遗忘时**广播复习提醒**。

赛题三大挑战的对应：


| 挑战       | 我们的回答                                                                                                                                                                                                                | 大白话                                                         |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| ① 重新定义记忆 | 企业记忆 ≠ 聊天日志，而是 **"带时间戳的结构化决策图谱（Decision Graph）"**：节点 = 决策 / 理由 / 反对意见 / 结论，边 = supersede / supports / conflicts / depends-on。CLI 高频命令、飞书文档变更只是**触发器**，真正沉淀的是"为什么这样做"。                                                | 我们不存"昨天谁说了啥"，我们存"为什么我们这么干、当时谁反对、谁拍板"。这才是企业真正会反复用到的东西。       |
| ② 构建记忆引擎 | 在 `nanobot/agent/hiarch_memory/` 已有的 STM + Episodic(LightRAG) 之上，新增 **Decision Layer**（结构化 SQLite + 图）+ **Forgetting Scheduler**（cron 周期衰减），通过 `nanobot/skills/memory/` 暴露 `recall / inject / review`，CLI 与飞书共享同一存储。 | 不重造轮子，在仓库现有的"短期记忆 + 情景记忆"上加一层"决策抽屉"。CLI 写进去的，飞书也能读出来；反之亦然。  |
| ③ 证明价值   | 自建 50 条**决策评测集**（DecisionBench），指标：决策召回率、重复争论拦截率、复习提醒命中率、Token 节省率，对照实验 vs 朴素 RAG。                                                                                                                                   | 不靠"看起来很聪明"忽悠评委，我们用 50 道题打分，并和"普通 ChatGPT + 全量塞文档"做对比，让数字说话。 |


---

## 0.2 三个用户故事（让评委秒懂场景）

### 故事 ① "重启旧争论拦截"（核心 Demo）

> **场景**：项目群里。  
> 新同事 @机器人："我觉得我们后端应该用 Session 鉴权，方便。"  
> **DecisionMind**（自动弹出卡片）：
>
> > 📌 **历史决策回顾**（决策于 2 周前，参与人 @张三 @李四 @王五）  
> > **结论**：采用 JWT，否决 Session  
> > **理由**：① 微服务无状态；② 移动端长连接需要；③ 已有 SDK  
> > **反对意见（已记录）**：李四曾担心 token 泄露，已通过短 TTL + refresh 解决  
> > **关联截止日**：2026-05-05 上线（剩 8 天 ⏰）  
> > [👍 仍然有效] [✏️ 我要更新] [🗑 已过期]

### 故事 ② "遗忘曲线复习"（方向 D 价值点）

> **场景**：3 周前 CTO 在群里发过"客户 ABC 的 API 密钥已轮换为 KEY_v2"。  
> 系统按艾宾浩斯曲线算到第 19 天记忆强度跌破阈值，**主动在群里发卡片**：
>
> > 🔔 **重要事项即将被遗忘 - 来复习一下**  
> > 客户 ABC 当前生效密钥：`KEY_v2`（旧 `KEY_v1` 已废弃）  
> > 上次提及：3 周前 by @CTO  
> > [✅ 我记住了] [📌 钉到群顶] [❌ 不再重要]

### 故事 ③ "CLI ↔ 飞书互通"（吃方向 A 的分）

> **场景**：开发者在终端：
>
> ```bash
> $ claw memory inject --topic="部署策略" --content="生产环境只在周二/周四发版"
> ✓ 已写入决策记忆（id=dec_8a3f, 已同步至飞书"研发群"）
>
> $ claw memory recall "什么时候能发版"
> 📌 部署策略（决策于今天，by you）
>    生产环境只在周二/周四发版
>    关联讨论：飞书研发群 message_id=...
> ```

> 这三个故事就是 Demo 视频的三幕剧脚本，评委一眼能 get 价值。

---

## 1. 现状盘点（基于本仓库实际代码）

> **先盘家底，再决定要造什么**——这是避免无谓重复工作的第一步。


| 已有能力                    | 在仓库中的位置                                                     | 我们怎么复用                                | 说人话                                  |
| ----------------------- | ----------------------------------------------------------- | ------------------------------------- | ------------------------------------ |
| 飞书长连接 + 流式卡片            | `nanobot/channels/feishu.py`                                | 直接复用，新增"决策卡片"模板                       | 飞书机器人收发消息这套已经写好了，我们只加一种新卡片样式         |
| 短期记忆 / 滑动窗口             | `nanobot/agent/hiarch_memory/shorterm.py`                   | 作为决策抽取的输入流                            | 最近 N 条聊天记录已经在内存里，直接拿来喂 LLM 抽决策       |
| 情景记忆 + LightRAG + Neo4j | `nanobot/agent/hiarch_memory/episodic.py`                   | 复用图存储能力，扩展决策子图                        | 向量库 + 图数据库已经接好，决策只是新加几个节点类型          |
| 记忆聚合入口                  | `nanobot/agent/hiarch_memory/memory.py::aggregation_memory` | 新增 Router：意图分发到 decision / episodic   | 大模型每次回话前会调一次这个函数，我们在里面加个"是否触及旧决策"的判断 |
| Skill 注册框架              | `nanobot/skills/memory/SKILL.md`                            | 新增 `decision` skill，暴露工具给 LLM         | 让大模型自己学会调用 `recall_decision()`，不用硬编码 |
| CLI 框架                  | `nanobot/cli/commands.py` + `nanobot/command/`              | 新增 `claw memory recall/inject/review` | 命令行已经有 `claw` 入口，加 3 个子命令即可          |
| 定时任务                    | `nanobot/cron/`                                             | 跑遗忘衰减 + 复习扫描                          | 后台轮询机制已存在，注册一个新 job 就行               |
| Provider 结构化输出          | `episodic.py::chat_scheme`                                  | 直接套用 `Decision` Pydantic schema       | 让 LLM 输出 JSON 而不是自由文本，这能力已封装好        |


**结论**：底座基本齐备，方向 B/D 不需要大改架构，**新增 1 个层（Decision Layer）+ 2 个 skill + 1 个 cron 即可**。预估真正需要写的新代码 < 1500 行。

---

## 2. 重新架构：在现有 Hiarch Memory 上加 "Decision Layer"

> 本节先从"一眼能看懂"的全景图出发，再逐层下钻到调用时序、存储方案、各子模块 I/O、代码改动边界，最后是每个核心算法的白话 + 伪代码。

---

### 2.0 先看懂"非结构化"和"结构化"的根本区别

在动手讲架构之前，先解答"我们到底在存什么"——这是整个系统价值的根基。

**场景还原**：飞书群里有这样一段对话

```
产品经理 A (10:00)：咱们搜索功能，用 ElasticSearch 还是 Algolia？
后端研发 B (10:05)：我倾向自己搭 ES，免费，数据在自己手里，安全。
技术总监 C (10:12)：自己搭后期运维成本太高了。Algolia 开箱即用，我们赶进度，
                   没时间折腾 ES 调优。
后端研发 B (10:15)：也是，下个月就要上线，确实来不及。
产品经理 A (10:18)：那就这么定了，先上 Algolia。B，周五前出接入方案文档。
```


| 方式                    | 存成什么       | 两个月后能干什么                       |
| --------------------- | ---------- | ------------------------------ |
| **录音笔**（原始聊天日志）       | 五行文本       | 只能关键词搜索，找不到"为什么否了 ES"          |
| **DecisionMind**（结构化） | 一张决策卡片（见下） | 新人问"为什么不用 ES"→ 一秒弹出卡片，直接终结无效争论 |


DecisionMind 生成的决策卡片：

```
🎯 决策议题：下一版搜索功能的技术选型（ES vs Algolia）
⚖️ 理由与交锋：
   支持 ES：数据安全、免费（研发 B 提）
   反对 ES / 支持 Algolia：赶进度、ES 运维成本高（总监 C 拍板）
✅ 最终结论：采用 Algolia
📅 执行项：研发 B 周五前出接入方案文档
👥 参与人：A / B / C
🔗 来源：飞书群 message_id=om_xxxxxx（可点击跳回）
```

**一句话概括**：非结构化记忆是**录音笔**，只能回放；结构化决策记忆是**会议纪要秘书**，能提炼、归档，并在你快要犯错时把那一页准确地翻出来递给你。

---

### 2.1 整体架构全景图（带白话标注）

```
╔══════════════════════════════════════════════════════════════╗
║  入口层 Channel Layer                                        ║
║  feishu.py（飞书群/私聊）        cli/commands.py（命令行）   ║
║  用户的两个入口，统一转换成 InboundMessage 事件              ║
╚═══════════════════╤══════════════════════╤═══════════════════╝
                    │ 入站消息              │ ↑ 主动推送 / 卡片
                    ▼                      │
╔══════════════════════════════════════════╧═══════════════════╗
║  Agent Loop  (nanobot/agent/loop.py)                         ║
║  每条消息都要走这里。它负责：                                ║
║  1. 从 Session 取历史 → ShortTermMemory 重建                ║
║  2. 调 ContextBuilder.build_system_prompt()  拼提示词        ║
║  3. 把拼好的提示词 + 消息 → Provider（大模型）               ║
║  4. 流式返回结果 → Channel 输出                              ║
╚═══════════════════╤══════════════════════════════════════════╝
                    │ 调 aggregation_memory(current_message)
                    ▼
╔══════════════════════════════════════════════════════════════╗
║  记忆聚合层 HiarchMemoryStore  (hiarch_memory/memory.py)     ║
║                                                              ║
║  ┌──────────────────────────────────────────────────────┐   ║
║  │  Router（意图路由，NEW）                              │   ║
║  │  判断：这条消息是否触及某个已有决策的 topic？          │   ║
║  │  - 是 ──→ DecisionMemoryStore.recall(topic)          │   ║
║  │  - 否 ──→ EpisodicMemoryStore.retrieve(msg) 兜底     │   ║
║  └──────────────────────────────────────────────────────┘   ║
║                                                              ║
║  ★ Decision Layer（NEW）         已有层（保持不变）          ║
║  ┌────────────────────┐          ┌──────────────────────┐   ║
║  │ DecisionMemoryStore│          │ EpisodicMemoryStore   │   ║
║  │ extract()          │          │ (LightRAG + Neo4j)    │   ║
║  │ store()            │◄─写──────│                       │   ║
║  │ recall()           │          └──────────────────────┘   ║
║  │ decay()            │          ┌──────────────────────┐   ║
║  │ supersede()        │          │ ShortTermMemoryStore  │   ║
║  └────────┬───────────┘          │ (滑动窗口，.jsonl)    │   ║
║           │ 存储                  └──────────┬───────────┘   ║
║  ┌────────▼───────────┐                     │ 满了→触发抽取  ║
║  │  decisions.db      │◄────────────────────┘               ║
║  │  (SQLite，结构化)   │                                     ║
║  │  + LightRAG KV图   │                                     ║
║  └────────────────────┘                                     ║
╚═══════════════════════════════════════════╤══════════════════╝
                                            │
                    ┌───────────────────────┘
                    │ 独立后台进程
                    ▼
╔══════════════════════════════════════════════════════════════╗
║  定时任务层  nanobot/cron/decision_review.py（NEW）           ║
║  每小时扫描 decisions.db → 计算 R(t) → R<0.4 且 importance>0.6║
║  → 发复习卡片到对应飞书群                                    ║
╚══════════════════════════════════════════════════════════════╝
```

**这张图怎么读**（从上往下 5 步）：

1. 用户在**飞书或命令行**发消息 → `loop.py` 收到事件。
2. `loop.py` 在准备喂给大模型之前，先调 `ContextBuilder.build_system_prompt()`。
3. `build_system_prompt` 的核心一句就是 `await self.memory.aggregation_memory(current_message)`——这是记忆引擎的"总入口"。
4. 记忆引擎里新加了一个 **Router**，先问："这条消息和某个历史决策有没有关系？"有关系就去**决策抽屉**（DecisionMemoryStore）取，没有就走原有的**情景记忆**（LightRAG）。
5. 后台独立跑一个 **cron 任务**，不依赖用户消息，自己定时扫"快被遗忘的决策"然后推卡片。

---

### 2.2 逐层代码改动边界（"动什么 / 不动什么"一目了然）

```
nanobot/
├── agent/
│   ├── loop.py                   ── 不动（已有钩子够用）
│   ├── context.py                ── 不动（aggregation_memory 入口已存在）
│   ├── hiarch_memory/
│   │   ├── memory.py             ── 小改：aggregation_memory 里加 Router 逻辑
│   │   ├── shorterm.py           ── 小改：rebuild_history 里加 extract 钩子
│   │   ├── episodic.py           ── 不动（复用 chat_scheme / LightRAG）
│   │   ├── decision.py           ★★ 全新文件（核心，~600 行）
│   │   ├── base.py               ── 不动
│   │   ├── semantic.py           ── 不动（占位，未实现）
│   │   └── working.py            ── 不动（占位，未实现）
├── channels/
│   └── feishu.py                 ── 小改：新增 build_decision_card() 函数
├── cli/
│   └── commands.py               ── 小改：新增 memory inject/recall/review 子命令
├── cron/
│   └── decision_review.py        ★★ 全新文件（遗忘扫描，~200 行）
├── skills/
│   └── decision/
│       └── SKILL.md              ★★ 全新 skill（暴露 recall_decision 给 LLM）
templates/
└── custom/
    └── decision_extract.md       ★★ 全新 Prompt 模板（~50 行）
```

**改动量化**：全新文件约 850 行；小改文件累计约 200 行；不动文件 0 行风险。

---

### 2.3 调用时序图（一次普通对话从头到尾发生了什么）

以"用户在飞书群发消息触发历史决策推送"为例：

```
飞书用户      feishu.py     loop.py      context.py    memory.py    decision.py
   │             │             │             │             │             │
   │──发消息─────▶│             │             │             │             │
   │             │──InboundMsg▶│             │             │             │
   │             │             │──rebuild_history (STM)                  │
   │             │             │  ├─历史未满 → 跳过                       │
   │             │             │  └─历史满了 → extract()──────────────────▶
   │             │             │                           │  LLM提取决策 │
   │             │             │                           │◀─Decision列表─│
   │             │             │                           │──store()──────▶
   │             │             │                           │  写入SQLite    │
   │             │──build_system_prompt(msg)───────────────▶             │
   │             │             │──aggregation_memory(msg)──▶             │
   │             │             │             │──Router判断──▶             │
   │             │             │             │  topic命中   │             │
   │             │             │             │──recall()────────────────▶│
   │             │             │             │              │  混合检索   │
   │             │             │             │◀──决策摘要───────────────│
   │             │             │◀──system prompt（含决策）──│             │
   │             │──LLM调用───▶│             │             │             │
   │             │◀──流式回复──│             │             │             │
   │◀──飞书卡片──│             │             │             │             │
```

**另一条路径：后台 cron 主动推送**（与用户消息完全无关）

```
cron/decision_review.py        decisions.db          feishu.py
         │                          │                     │
         │──每小时触发───────────────▶                     │
         │◀─所有 active 决策────────│                     │
         │──计算 R(t) = exp(-Δt/S)  │                     │
         │──筛选 R<0.4 且 importance>0.6                  │
         │──更新 last_reviewed_at────▶                     │
         │──build_review_card()──────────────────────────▶│
         │                                                │──推送复习卡到群
```

---

### 2.4 存储层详解（决策到底存在哪里，怎么存）

决策数据采用**双写策略**：结构化事实写 SQLite，语义关系写 LightRAG KV 图。

#### SQLite 表结构（`decisions.db`）

```sql
-- 主表：每条决策的完整事实
CREATE TABLE decisions (
    id               TEXT PRIMARY KEY,    -- uuid hex[:8]
    project          TEXT NOT NULL,       -- 群 chat_id
    topic            TEXT NOT NULL,       -- 归一化主题 snake_case
    statement        TEXT NOT NULL,       -- 一句话结论
    reasons          TEXT NOT NULL,       -- JSON array
    objections       TEXT NOT NULL,       -- JSON array
    alternatives     TEXT NOT NULL,       -- JSON array
    decided_at       INTEGER NOT NULL,    -- Unix timestamp
    deadline         INTEGER,             -- nullable
    participants     TEXT NOT NULL,       -- JSON array of open_id
    source           TEXT NOT NULL,       -- chat/doc/cli/manual
    source_ref       TEXT NOT NULL,       -- message_id / doc_token
    importance       REAL NOT NULL DEFAULT 0.5,
    -- 遗忘曲线字段
    last_reviewed_at INTEGER NOT NULL,
    review_count     INTEGER NOT NULL DEFAULT 0,
    strength         REAL NOT NULL DEFAULT 1.0,  -- S 参数
    supersedes       TEXT,                -- 旧决策 id，nullable
    status           TEXT NOT NULL DEFAULT 'active'
);

-- 加速检索的索引
CREATE INDEX idx_project_topic     ON decisions(project, topic);
CREATE INDEX idx_status_importance ON decisions(status, importance);
CREATE INDEX idx_last_reviewed     ON decisions(last_reviewed_at);
```

#### LightRAG 图层（复用 `episodic.py` 的 `_rag` 实例）

决策被存入 LightRAG 时以如下文本格式插入，LightRAG 自动抽取实体-关系写入图：

```
[DECISION dec_8a3f] topic=auth_strategy
statement: 采用 JWT，否决 Session
reasons: 微服务无状态; 移动端长连接; 已有SDK
objections: token泄露风险（已通过短TTL+refresh解决）
alternatives: Session鉴权
participants: 张三; 李四; 王五
decided_at: 2026-04-10
```

图中生成的节点 / 边示例：

- 节点：`JWT` / `Session` / `auth_strategy` / `研发群`
- 边：`auth_strategy --采用→ JWT`，`auth_strategy --否决→ Session`，`JWT --supersedes→ Session`

在 recall 时走 LightRAG 的 `hybrid` 模式（语义向量 + 图关系联合检索），精准度远高于纯向量。

---

### 2.5 决策数据结构（我们到底在记什么？）

> **类比**：把每个决策想成"一张可以打补丁的便利贴"。`statement` 是正面写的结论，`reasons/objections` 是背面记的"为什么"，`supersedes` 是粘在它前面的旧便利贴。

```python
# nanobot/agent/hiarch_memory/decision.py  (NEW)
class Decision(BaseModel):
    id: str
    project: str                # 关联项目/群聊 id
    topic: str                  # 归一化主题，e.g. "auth_strategy"
    statement: str              # 结论，一句话（"采用 JWT 鉴权"）
    reasons: list[str]          # 支持理由（为什么选它）
    objections: list[str]       # 反对意见 / 风险（谁担心什么）
    alternatives: list[str]     # 被放弃的方案 ("Session 鉴权")
    decided_at: int             # 决策时间戳
    deadline: int | None        # 关联截止日（方向 B 关键）
    participants: list[str]     # open_id 列表（谁在场）
    source: Literal["chat","doc","cli","manual"]
    source_ref: str             # message_id / doc_token（可回溯到原始证据）
    importance: float           # 0~1（核心决策接近 1，琐事接近 0）
    # —— 方向 D：遗忘曲线字段 ——
    last_reviewed_at: int       # 上次被翻出来用的时间
    review_count: int           # 被翻出来过几次
    strength: float             # 记忆强度 S，每次 review 增大（间隔重复）
    supersedes: str | None      # 旧决策 id（这条是更新版的话）
    status: Literal["active","superseded","expired"]
```

**为什么这样设计？**——每个字段都对应一个真实痛点：


| 字段                                    | 不设它会怎样                                             |
| ------------------------------------- | -------------------------------------------------- |
| `reasons / objections / alternatives` | 只存结论的话，团队会反复争论"我们当时为什么否了 A？"——这是赛题原话点到的痛点。         |
| `deadline`                            | 方向 B 题面里强调"上周五确认了截止日期是 5 号"——不存 deadline 就接不住这个场景。 |
| `participants`                        | 没法追溯责任人；新人看到决策也不知该 @ 谁问。                           |
| `source_ref`                          | 评委质疑"你这个决策是真的吗？"——能一键跳回原始飞书消息就赢了。                  |
| `strength + last_reviewed_at`         | 没这俩字段就跑不出艾宾浩斯曲线，方向 D 直接落空。                         |
| `supersedes + status`                 | 新旧决策共存会害死团队（"咦怎么有两个版本？"）；版本链让 AI 永远只引用最新有效版。       |


---

### 2.6 关键算法详解（每个配伪代码 + 白话）

#### a. 抽取（Extract）—— 从聊天里挑出真决策

**触发位置**：`shorterm.py::rebuild_history()` 在历史条数超过 1000 时，把要"清理"的那批消息送去抽取，复用现有钩子，不增加额外 LLM 调用频率。

**Prompt 设计**（`templates/custom/decision_extract.md`，节选）：

```
你是一位会议纪要专家。请从以下对话中识别所有"决策事件"。
每条决策必须满足：① 有明确结论（某人拍板或形成共识）② 有可辨别的议题。
闲聊、问题、进度同步不算决策。
请严格按 JSON schema 输出，不要自由发挥...
```

**伪代码**：

```python
async def extract(self, messages: list[dict]) -> list[Decision]:
    text = self._format_messages(messages)         # 同 episodic.py 的方式
    self._provider.set_scheme(DecisionListResult)  # Pydantic schema 约束输出
    response = await self._provider.chat_scheme(
        [{"role": "system", "content": EXTRACT_PROMPT},
         {"role": "user",   "content": text}],
        model=self._model, tools=None
    )
    decisions = response.parsed["result"]          # List[Decision]
    # 自检：过滤 importance < 0.3 的噪音
    return [d for d in decisions if d.importance >= 0.3]
```

**白话**：把最近 100 条聊天甩给 LLM，让它用"会议纪要专家"的身份填一张表格（`Decision` schema）——不允许自由发挥，必须输出结构化 JSON。空表格行直接丢弃。

---

#### b. 存储（Store）—— 写入双层存储

```python
async def store(self, decisions: list[Decision]) -> None:
    for d in decisions:
        # 1. 写 SQLite（事实存储，毫秒级）
        self._sqlite_upsert(d)

        # 2. 检查是否需要 supersede 旧决策
        old = self._find_conflicting(d.topic, d.project)
        if old and await self._is_conflict(old, d):    # LLM 二次裁决
            self._mark_superseded(old.id, new_id=d.id)

        # 3. 写 LightRAG 图（异步，不阻塞主流程）
        asyncio.create_task(
            self._rag.ainsert(self._decision_to_text(d))
        )
```

**白话**：先快速存进 SQLite（保证持久化），然后异步更新图数据库（不卡用户响应），中间顺便检查有没有旧决策要被覆盖。

---

#### c. 召回（Recall）—— 三路混合检索

```python
async def recall(self, query: str, project: str, top_k: int = 3
                 ) -> list[Decision]:
    # 路径 1：语义向量（LightRAG hybrid，最模糊最广）
    rag_text = await self._rag.aquery(query, QueryParam(mode="hybrid"))
    candidate_ids = self._parse_ids_from_rag_text(rag_text)

    # 路径 2：SQLite 精确 topic 匹配（最快，覆盖 exact match）
    topic = self._extract_topic(query)              # 关键词 → topic
    sql_ids = self._sqlite_query_by_topic(topic, project)

    # 路径 3：时序权重加成（最近 7 天的决策权重 ×1.5）
    all_ids = set(candidate_ids) | set(sql_ids)
    decisions = self._load_by_ids(all_ids)

    # 综合打分：语义分×0.5 + topic精确×0.3 + 时序加成×0.2
    scored = self._rank(decisions, query)

    # 命中后更新遗忘曲线（间隔重复强化）
    for d in scored[:top_k]:
        self._reinforce(d)   # S *= 1.8, last_reviewed_at = now
    return scored[:top_k]
```

**白话**：先用"模糊联想"（向量）找一批，再用"精确对词"（SQL）找一批，合并后按时间新旧打分排序，取前 3 名。命中的决策顺手给"记忆强度"充值，让它下次更慢被遗忘。

---

#### d. 遗忘曲线（Decay）—— 让旧决策自然老化

**公式**：$R(t) = e^{-\Delta t / S}$


| 参数  | 含义                       | 初始值                    |
| --- | ------------------------ | ---------------------- |
| R   | 当前记忆强度（0 = 完全忘了，1 = 刚记住） | —                      |
| Δt  | 距上次 review 的天数           | —                      |
| S   | 记忆稳定性（越大衰减越慢）            | `1.0 × importance × 5` |


**间隔重复效果**：每次被 recall 命中 → `S *= 1.8`。一个决策被用了 5 次后，S 已从初始值涨约 18 倍，需要接近 100 天才会跌破遗忘阈值。

**复习触发条件**（在 cron job 里每小时计算一次）：

```python
def should_review(d: Decision) -> bool:
    delta_t = (now() - d.last_reviewed_at) / 86400   # 换算成天
    R = math.exp(-delta_t / d.strength)
    return R < 0.4 and d.importance > 0.6 and d.status == "active"
```

**三种场景白话**：

- 天天被用到的决策（反复 recall）→ S 不断涨 → 衰减变慢 → 永远不会被提醒
- 很重要但一直没被提到的决策 → S 不涨 → 约 5 天后跌破 0.4 → cron 发提醒
- 不重要且没被用到的决策 → R 也跌，但 importance ≤ 0.6 → 直接淡出，不烦人

---

#### e. 版本覆盖（Supersede）—— 新决策替换旧决策

**触发条件**：新抽到的决策与数据库中某条 `active` 决策的 `topic` 完全相同（或 Jaccard 相似度 > 0.8）且 `statement` 向量距离 > 0.5（说明方向相反）。

```
         旧决策（status=active）
            │ dec_001: 采用 JWT
            │
新决策进来 ──▶ LLM 二次裁决："这俩是不是真的冲突？"
            │
           是 ──▶ dec_001.status = "superseded"
                  dec_001.superseded_by = dec_002
                  dec_002.supersedes    = dec_001
                  dec_002.status        = "active"
           否 ──▶ 两条共存（可能是不同子议题）
```

**版本链**（可无限溯源）：

```
dec_003（active）─supersedes─▶ dec_001（superseded）─supersedes─▶ dec_000（superseded）
```

**白话**：群里今天说"改用方案 C 了"，系统给上周"用方案 B"那张便利贴打个删除线，但**不丢**——以后还能查"为啥又改了"。  
**降级方案**（时间紧时）：跳过 LLM 二次裁决，纯规则版（topic 完全匹配即覆盖），损失约 5% 准确率但节省 LLM 调用。

---

### 2.7 主动推送逻辑详解（每条新消息触发一次实时检测）

```
用户消息进入 aggregation_memory()
          │
          ▼
  embed(current_message) ──→ 向量 v_q
          │
          ▼
  从 SQLite 加载所有 status=active 的决策向量（已预先存储 embedding）
          │
          ▼
  cosine_sim(v_q, v_decision) > 0.78 ？
          │
         是 ──▶ topic 模糊匹配（防止错误联想）？
                    │
                   是 ──▶ 将该决策以"📌 历史决策回顾"格式注入 system prompt
                           同时通过 feishu.py 异步发出交互卡片（不阻塞 LLM 调用）
                   否 ──▶ 跳过
         否 ──▶ 跳过，走 EpisodicStore 兜底
```

**飞书交互卡片结构**（CardKit JSON，B 负责实现）：

```
┌─────────────────────────────────────────────────────┐
│ 📌 历史决策回顾                                      │
│                                                     │
│ 议题：鉴权方案选型（auth_strategy）                  │
│ 决策于：2 周前  参与人：@张三 @李四 @王五             │
│ ─────────────────────────────────────────────────  │
│ ✅ 结论：采用 JWT，否决 Session                      │
│ 💡 理由：微服务无状态 / 移动端长连接 / 已有 SDK       │
│ ⚠️  反对（已解决）：token泄露风险，用短TTL+refresh   │
│ 🗑️  否决方案：Session 鉴权                          │
│ ⏰ 截止日：2026-05-05 上线（剩 8 天）                │
│ 🔗 [查看原始消息]                                   │
│                                                     │
│  [👍 仍然有效]  [✏️ 我要更新]  [🗑 已过期]           │
└─────────────────────────────────────────────────────┘
```

**按钮回调**写回 `DecisionMemoryStore`：

- "仍然有效" → `reinforce(id)`（S *= 1.8）
- "我要更新" → 打开编辑表单 → `store(new_decision, supersedes=id)`
- "已过期" → `mark_expired(id)`

---

## 3. 评测设计（挑战三）：DecisionBench-50

> 评委一定会问："你说你记住了，证据呢？"——所以**先设计指标，再写代码**。

### 3.1 五大指标


| 指标                     | 说人话定义                              | 怎么算                                          | 目标     |
| ---------------------- | ---------------------------------- | -------------------------------------------- | ------ |
| Decision-Recall@5      | 给一句新提问，前 5 条召回里有没有正确答案             | 命中数 / 总测试题数                                  | ≥ 0.85 |
| Repeat-Debate-Block    | 模拟"重提旧争论"，系统能不能主动拦下来               | 主动弹卡片次数 / 应该拦的次数                             | ≥ 0.75 |
| Forget-Alert-Precision | 复习提醒中，用户点"有用"的比例                   | 用户点 ✅ 的次数 / 推送次数                             | ≥ 0.70 |
| Token-Saved            | 比起朴素 RAG（把整堆历史塞 prompt），省了多少 token | 1 - 我们的 prompt token / baseline prompt token | ≥ 40%  |
| Latency                | 用户消息进来 → 卡片弹出来，几秒？                 | p95 端到端延时                                    | ≤ 2.5s |


### 3.2 测试集长啥样（一条样本示例）

```jsonl
{
  "id": "db_001",
  "history": [
    "[2026-04-10 14:00] 张三: API 鉴权我倾向 Session",
    "[2026-04-10 14:05] 李四: 我们是微服务，Session 不太行",
    "[2026-04-10 14:30] 王五: 拍板，用 JWT，李四的理由成立"
  ],
  "query": "我们鉴权方案到底是啥？",
  "expected_decision_id": "db_001_dec",
  "expected_topic": "auth_strategy",
  "should_block_alternatives": ["Session"],
  "deadline_aware": false
}
```

50 条样本中包含：

- 30 条**正面用例**（明确的决策抽取与召回）
- 10 条**supersede 用例**（新决策覆盖旧决策）
- 10 条**干扰用例**（看起来像决策但其实只是闲聊，考验抗噪）

存放路径：`docs/bench/decisionbench.jsonl`

### 3.3 对照实验（让数字会说话）


| 系统                    | 描述                  |
| --------------------- | ------------------- |
| **Baseline-A**：朴素 LLM | 不接任何记忆，纯 GPT 答      |
| **Baseline-B**：朴素 RAG | 把所有历史聊天塞向量库，TopK 召回 |
| **Ours**：DecisionMind | 决策层 + 遗忘曲线 + 主动推送   |


预期结果（Demo 时画成柱状图给评委看）：Recall 提升 30%+，Token 节省 40%+，主动拦截能力是另两者所没有的（直接 N/A）。

---

## 4. 三人团队 9 天作战计划

> **角色定义**（每人聚焦一块物理代码区，最小化合并冲突）：
>
> - **A · Memory Core**（懂 Python/RAG/图）：决策抽取、存储、衰减算法 → 主战区 `nanobot/agent/hiarch_memory/`
> - **B · Channel & UX**（懂飞书 SDK/卡片/CLI）：飞书卡片、CLI 命令、主动推送 → 主战区 `nanobot/channels/` + `nanobot/cli/` + `nanobot/cron/`
> - **C · Eval & Product**（懂指标/数据/Prompt）：DecisionBench、Prompt 工程、Demo 脚本 → 主战区 `docs/` + `templates/` + `scripts/`

### 4.1 全景甘特图（粗粒度）

```
Day:        1   2   3 │ 4   5   6 │ 7   8   9
            ─────────╫───────────╫───────────
Sprint：       打地基 │   见智能   │   出 Demo
Milestone:        ▲          ▲           ▲
                M1:          M2:         M3:
              抽 1 条→存    召回+遗忘+   完整 Demo
              飞书能渲染    版本+评测     视频+报告
打卡：            ★          ★           ★
            Day3 复盘   Day6 复盘   Day9 复盘
```

### Sprint 1（Day 1–3）：打地基 — "能抽出决策 + 能存进去"

> **本 Sprint 一句话目标**：跑通最小闭环——一段对话进去，一条结构化决策出来，并能在飞书显示。


| 成员  | 任务                                                                                                                                              | 交付物                                          | 验收标准                                       |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------ |
| A   | 新建 `nanobot/agent/hiarch_memory/decision.py`，定义 `Decision` schema + `DecisionMemoryStore`（SQLite 落地 + 复用 LightRAG 图存储），实现 `extract() / store()` | 单测：给定 1 段对话，能产出结构化决策记录                       | `pytest tests/test_decision_extract.py` 全绿 |
| B   | 飞书侧：在 `channels/feishu.py` 增加"决策卡片"模板（标题/理由/反对/结论/时间）；CLI 侧：`nanobot/cli/commands.py` 新增 `claw memory inject --topic=...`                       | `claw memory inject` 可写入 1 条决策；飞书能渲染卡片       | 命令行写入 → 飞书群里 30 秒内出现卡片                     |
| C   | 编写 `docs/bench/decisionbench.jsonl` 前 20 条样例 + 抽取 Prompt v1（`templates/custom/decision_extract.md`）                                             | 20 条标注数据 + Prompt 文件；跑通 A 的抽取得到 baseline 准确率 | 至少 12/20 题抽对（Recall ≥ 0.6）                 |


**Day 3 联调点**：三人凑一起，把 C 的 20 条样本喂给 A 的抽取，B 把结果以卡片形式渲染在飞书——这一刻就是 M1 里程碑。

**Day 3 个人复盘记录** → 写入 `docs/logs/sprint1_<name>.md`（套 `TEMPLATE.md`），包含：① 学到了什么（如 LightRAG 图 schema、飞书 CardKit）② 完成了什么 ③ 阻塞点。

### Sprint 2（Day 4–6）：见智能 — "能召回 + 能遗忘 + 能 supersede"

> **本 Sprint 一句话目标**：从"会记"升级到"会用"——主动召回、主动遗忘、主动更新。


| 成员  | 任务                                                                                                                       | 交付物                                    | 验收标准                                         |
| --- | ------------------------------------------------------------------------------------------------------------------------ | -------------------------------------- | -------------------------------------------- |
| A   | 实现 `recall()` 混合检索（语义+图+时序）、`decay()` 遗忘曲线、`supersede()` 版本链；接入 `memory.py::aggregation_memory` 的 Router                 | `aggregation_memory` 在触及旧话题时返回决策摘要而非全文 | 在 50 条 bench 上 Recall@5 ≥ 0.75               |
| B   | `nanobot/cron/` 新增 `decision_review.py`：每小时扫描遗忘阈值 → 调 feishu 推送复习卡；CLI `claw memory recall/review` 完工；卡片支持"确认/废弃/更新"按钮回写 | 群聊里能自动收到复习提醒；点按钮能更新决策状态                | 模拟跳到 19 天后，群里能自动收到复习卡                        |
| C   | DecisionBench 扩展到 50 条；搭建评测脚本 `scripts/eval_decisionbench.py`；产出 Sprint1 baseline vs Sprint2 对比报告                        | 评测报告 v1，至少跑出 Recall@5 数字               | `python scripts/eval_decisionbench.py` 一键出报告 |


**Day 6 卡点检查**：如果 Recall@5 < 0.7 → 启动降级方案（Supersede 改纯规则版，省时间补抽取 prompt 调优）。

**Day 6 个人复盘** → `docs/logs/sprint2_<name>.md`。

### Sprint 3（Day 7–9）：出 Demo — "讲故事 + 出指标 + 防翻车"

> **本 Sprint 一句话目标**：把它打磨成评委 5 分钟内会"哇"的产品。


| 成员  | 任务                                                                                | 交付物                                  | 验收标准                 |
| --- | --------------------------------------------------------------------------------- | ------------------------------------ | -------------------- |
| A   | 性能优化：embedding 缓存、SQLite 索引、并发安全；修复评测中暴露的 bad case；冻结 API                         | 端到端延时 ≤ 2.5s；通过 50 条 bench           | 5 个并发用户测试无报错         |
| B   | 录制 3 分钟 Demo（飞书群"重启旧争论 → 卡片拦截"+"截止日临近 → 主动提醒"+"CLI 双端互通"）；写部署文档 `docs/deploy.md`  | Demo 视频 + 一键启动脚本 `run_demo.sh`       | 新人按文档 30 分钟内能跑起来     |
| C   | 完成最终评测报告（含对照实验：朴素 RAG vs Decision Layer），整理 PPT 与答辩 Q&A，更新主 `README.md` 的"开发更新日志" | `docs/report.md` + `docs/slides.pdf` | 答辩 Q&A 至少覆盖 10 个高频问题 |


**Day 9 个人复盘** → `docs/logs/sprint3_<name>.md` + 团队总结 `docs/logs/retro.md`。

### 4.2 三次打卡的统一模板（每人每 3 天填一次）

> 模板已放在 `docs/logs/TEMPLATE.md`，复制改名即可。这套打卡是赛题"过程证据"的硬核体现。

```markdown
# Sprint <N> · <Name> · <YYYY-MM-DD>
## 学习 (Learn)
- 知识点 1：（例：LightRAG 的 hybrid query 模式 = 语义 + 关键词混合检索）
- 知识点 2：（例：飞书 CardKit 的 streaming 模式需要 cardkit:card:write 权限）
## 完成 (Done)
- [x] 任务 / PR 链接
- [x] ...
## 数据 / 指标
- (e.g. Decision-Recall@5 = 0.62 → Sprint 2 目标 0.75)
## 阻塞 & 下一步
- 阻塞：...
- 明日计划：...
```

---

## 5. 风险与对策


| 风险                            | 概率  | 影响         | 对策                                                                                | 触发降级的标志            |
| ----------------------------- | --- | ---------- | --------------------------------------------------------------------------------- | ------------------ |
| LLM 抽决策幻觉 / 漏抽                | 高   | 决策错就全错     | Prompt 双轮 self-check + DecisionBench 守门                                           | Day 3 抽取准确率 < 0.6  |
| Neo4j 部署门槛                    | 中   | 评委复现失败     | 默认走 SQLite + LightRAG 内置 KV 图，Neo4j 列为可选                                          | 直接默认关闭             |
| 飞书 `cardkit:card:write` 权限申请慢 | 中   | 流式卡片做不出来   | 同步走普通卡片回退（仓库已支持 `streaming:false`）                                                | Day 1 申请未通过即降级     |
| 9 天时间紧                        | 高   | 关键功能砍      | Day 6 卡点：若评测未达 0.7，砍掉 supersede 的 LLM 二次裁决，改为规则版                                  | Sprint 2 评测报告      |
| 三人协作冲突                        | 中   | 合并代码灾难     | A 负责 `hiarch_memory/`、B 负责 `channels/+cli/+cron/`、C 负责 `docs/+scripts/`，物理隔离最小化冲突 | 每天 19:00 强制 rebase |
| Embedding 模型加载慢               | 低   | Demo 时启动卡顿 | 预热 + 容器化打包                                                                        | Demo 前 10 分钟启动     |


---

## 6. FAQ（评委大概率会问的问题，提前备好答案）

**Q1：你们和普通 RAG 的本质区别？**  
A：普通 RAG 检索"原文片段"，我们检索"结构化决策"。前者像在 Word 里 Ctrl+F，后者像在 Notion 数据库里筛选。决策有 supersede 链，能保证 AI 永远引用最新版。

**Q2：决策抽错了怎么办？**  
A：① 卡片有 [✏️ 我要更新] 按钮，用户一键修正并写回；② 评测集守门，准确率低于阈值 CI 不通过；③ supersede 机制让"错的决策"被"对的决策"覆盖而不是删除，可追溯。

**Q3：为什么不直接用飞书的 wiki 或者文档？**  
A：① 文档需要人主动写，95% 的决策死在群聊里；② 文档没有"主动推送"和"遗忘曲线"——这两个才是减负关键；③ 我们是通用记忆引擎，飞书只是入口之一，CLI 也能用。

**Q4：隐私和权限怎么处理？**  
A：① 决策按 `project` 维度隔离，对应飞书群的成员可见性；② 复用 nanobot 现有的 RBAC；③ 用户可以 `claw memory forget --id=...` 强制删除，satisfies "被遗忘权"。

**Q5：跟 ChatGPT 的 Memory 功能有啥不同？**  
A：① ChatGPT Memory 是个人级的，我们是**团队级 + 项目级**；② 我们的记忆是**结构化决策图**，不是松散的文本；③ 我们有**主动推送**，ChatGPT 是被动等问。

**Q6：9 天能做出来吗？**  
A：能。底座（飞书 SDK、LightRAG、cron、CLI）都是现成的，我们只写 Decision Layer（约 1500 行 Python）+ 评测集（50 条 jsonl）+ Demo 视频。已分配到三人具体到天的任务表，每 3 天有可验收里程碑。

**Q7：商业化路径？**  
A：① SaaS 订阅给中小团队（按群数量计费）；② 私有化部署给大企业（合规版）；③ 开源社区版做飞书生态获客，吃方向 A 的 CLI 用户群体。

---

## 7. 立即可执行的下一步（Day 1 上午）

1. **A**：`git checkout -b feat/decision-layer`，建空文件 `nanobot/agent/hiarch_memory/decision.py` 与 `templates/custom/decision_extract.md`。
2. **B**：调研现有 `channels/feishu.py` 中 CardKit 用法（搜索 `interactive` / `card`），起 `feat/decision-card` 分支，先做静态卡片。
3. **C**：建 `docs/bench/decisionbench.jsonl` 与 `docs/logs/`，把第一批 5 条样本写出来给 A 调 Prompt。
4. 全员：在飞书建"DecisionMind 研发群"，把 bot 拉进去做实时联调环境；约定每日 19:00 五分钟站会（飞书视频会议）。

> 一旦此文档通过评审，三人即按 §4 表格各自 fork 任务，每 3 天回到本仓库 `docs/logs/` 提交打卡 markdown，形成可追溯的过程证据。

---

## 附录 A · 名词对照表


| 术语                      | 中文         | 大白话                      |
| ----------------------- | ---------- | ------------------------ |
| STM (Short-Term Memory) | 短期记忆       | 最近 N 条聊天，类似人脑当下能记住的事     |
| Episodic Memory         | 情景记忆       | "上次开会聊了啥"，按时间索引的历史       |
| Semantic Memory         | 语义记忆       | "公司组织架构"等永久性事实，不带时间感     |
| Decision Layer          | 决策层（我们新加的） | 专门记"决定+理由+结论"的结构化抽屉      |
| Supersede               | 覆盖         | 新决策替代旧决策，但旧的不删，留痕        |
| Ebbinghaus Curve        | 艾宾浩斯遗忘曲线   | 人脑遗忘速度的数学公式，1885 年提出     |
| Spaced Repetition       | 间隔重复       | 复习一次后，下次复习的间隔变长（Anki 算法） |
| LightRAG                | 轻量图 RAG    | HKUDS 的开源库，把文档变成知识图谱再检索  |
| CardKit                 | 飞书卡片工具包    | 飞书提供的富交互卡片 SDK，支持流式更新    |
| RBAC                    | 基于角色的访问控制  | 谁能看哪些决策，按角色配             |


---

## 附录 B · 目录结构（完成后的仓库快照）

```
Feishu-Nanobot/
├── nanobot/
│   ├── agent/
│   │   └── hiarch_memory/
│   │       ├── decision.py          ★ 决策记忆核心模块（新建）
│   │       ├── memory.py            ★ 加 Router（小改）
│   │       ├── shorterm.py          ★ 加 extract 钩子（小改）
│   │       └── episodic.py          （不动）
│   ├── channels/
│   │   └── feishu.py                ★ 加 build_decision_card()（小改）
│   ├── cli/
│   │   └── commands.py              ★ 加 memory 子命令（小改）
│   ├── cron/
│   │   └── decision_review.py       ★ 遗忘曲线扫描（新建）
│   └── skills/
│       └── decision/
│           └── SKILL.md             ★ 决策 skill（新建）
├── templates/
│   └── custom/
│       └── decision_extract.md      ★ 抽取 Prompt（新建）
├── docs/
│   ├── bench/
│   │   └── decisionbench.jsonl      ★ 50 条评测集（新建）
│   ├── logs/
│   │   ├── TEMPLATE.md              ★ 打卡模板（新建）
│   │   ├── sprint1_A.md             ★ Day 3 打卡
│   │   ├── sprint2_A.md             ★ Day 6 打卡
│   │   └── sprint3_A.md             ★ Day 9 打卡
│   ├── mds/
│   │   ├── design.md                （原有）
│   │   └── proposal.md              ★ 本文件
│   └── report.md                    ★ 最终评测报告（Sprint 3）
└── scripts/
    └── eval_decisionbench.py        ★ 评测脚本（新建）
```

