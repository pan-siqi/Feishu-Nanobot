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

### 2.0 一张图看懂数据怎么流（带白话标注）

```
┌─────────────────────────────────────────────────────────────┐
│   Channel Layer：feishu.py  /  cli/commands.py              │
│   （用户的两个入口：飞书群 & 命令行，都接到同一个大脑）       │
└────────────┬────────────────────────────────┬───────────────┘
             ↓ 入站消息                        ↑ 主动推送 / 卡片
┌─────────────────────────────────────────────────────────────┐
│   Agent Loop (agent/loop.py)                                │
│        ↓ context.py::_build_system_prompt                   │
│   HiarchMemoryStore.aggregation_memory(msg)                 │
│   ┌──────────────┐  Router (意图分类: 是否触及历史决策?)     │
│   │   Router     │ ───→ DecisionStore.recall(topic) 命中走这 │
│   └──────┬───────┘ ───→ EpisodicStore.retrieve(msg) 兜底走这 │
│          ↓                                                  │
│   ┌──────────────────────────────────────────────────┐      │
│   │  ★ NEW: DecisionMemoryStore                      │      │
│   │  - extract():  LLM + Pydantic → Decision         │  抽   │
│   │  - store():    SQLite(决策事实) + Neo4j(决策图)   │  存   │
│   │  - recall():   语义+图混合检索 + 时序权重          │  取   │
│   │  - decay():    Ebbinghaus  R = e^(-t/S)          │  忘   │
│   │  - supersede(): 新决策覆盖旧决策（版本链）         │  新   │
│   └──────────────────────────────────────────────────┘      │
│          ↑ 写                       ↓ 读                    │
│   ShortTerm  Episodic(LightRAG)  Working  Semantic          │
│   （短期）   （情景，旧）         （工作）  （语义）         │
└─────────────────────────────────────────────────────────────┘
             ↑ cron/decision_review.py
       每小时扫描 → 命中遗忘阈值 → 飞书群"复习卡片"
```

**这张图怎么读**（从上往下）：

1. 用户在**飞书或命令行**说话 → 进入 Agent。
2. Agent 在拼系统提示词时，会调 `aggregation_memory()` 这个"记忆助理"。
3. 助理里有个 **Router**（路由器）先判断："这条消息是不是在聊一个旧决策？"
  - 是 → 找 `DecisionMemoryStore`（新加的"决策抽屉"）
  - 否 → 走原有的情景记忆（聊过什么）
4. 写入侧：每次短期记忆满了要"清理"时，顺手让 LLM 抽一遍决策塞进抽屉。
5. 后台 cron 每小时扫一遍："哪些决策快被忘了？"→ 主动推送复习卡到飞书群。

### 2.1 决策数据结构（我们到底在记什么？）

> **类比**：把每个决策想成"一张可以打补丁的便利贴"。statement 是正面写的结论，reasons/objections 是背面记的"为什么"，supersedes 是粘在它前面的旧便利贴。

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
    source_ref: str             # message_id / doc_token (可回溯到原始证据)
    importance: float           # 0~1（核心决策接近 1，琐事接近 0）
    # —— 方向 D：遗忘曲线字段 ——
    last_reviewed_at: int       # 上次被翻出来用的时间
    review_count: int           # 被翻出来过几次
    strength: float             # 记忆强度 S，每次 review 增大（间隔重复）
    supersedes: str | None      # 旧决策 id（这条是更新版的话）
    status: Literal["active","superseded","expired"]
```

**为什么这样设计？**——以下是字段背后的产品考量（每条都对应一个真实痛点）：


| 字段                                    | 不设它会怎样                                             |
| ------------------------------------- | -------------------------------------------------- |
| `reasons / objections / alternatives` | 只存结论的话，团队会反复争论"我们当时为什么否了 A？"——这是赛题原话点到的痛点。         |
| `deadline`                            | 方向 B 题面里强调"上周五确认了截止日期是 5 号"——不存 deadline 就接不住这个场景。 |
| `participants`                        | 没法追溯责任人；新人看到决策也不知该 @ 谁问。                           |
| `source_ref`                          | 评委质疑"你这个决策是真的吗？"——能一键跳回原始飞书消息就赢了。                  |
| `strength + last_reviewed_at`         | 没这俩字段就跑不出艾宾浩斯曲线，方向 D 直接落空。                         |
| `supersedes + status`                 | 新旧决策共存会害死团队（"咦怎么有两个版本？"）；版本链让 AI 永远只引用最新有效版。       |


### 2.2 关键算法（每个都配白话解读）

#### a. 抽取（Extract）—— 从聊天里挑出真决策

- **怎么做**：复用 `episodic.py` 的 `chat_scheme`，写一个新 Prompt（`templates/custom/decision_extract.md`），让 LLM 输出 `Decision` 这个 Pydantic 对象。
- **白话**：把最近 100 条聊天甩给 GPT，让它回答"这堆话里有几条算决策？分别是啥结论、啥理由、谁反对？"——但不让它自由发挥，必须填我们的表格（schema）。
- **触发时机**：每次短期记忆窗口满了要"卸货"时顺手抽一次（复用现有 `shorterm.rebuild_history` 的钩子，不增加 LLM 调用频率）。

#### b. 遗忘曲线（Decay）—— 让旧决策慢慢变淡

- **公式**：$R(t) = e^{-\Delta t / S}$  
  - R = 当前记忆强度（0~1，越接近 1 越"清晰"）
  - Δt = 距离上次访问的天数
  - S = 稳定性参数（一开始 = `1 day × importance × 5`）
- **间隔重复**：每次 recall 命中（说明还有用）→ `S *= 1.8`，下次衰减得更慢。这就是 Anki 闪卡背单词的同款算法。
- **复习触发**：当 `R < 0.4` **且** `importance > 0.6` → 进入复习队列，cron 推卡片到群。
- **白话**：天天用的东西不会忘；一周没碰的次要事项就让它淡掉；重要又快淡的——主动叫一下。

#### c. 主动推送（Proactive Push）—— 怎么知道现在该弹卡片

- **流程**：用户新消息 → 生成 embedding → 与所有 `status=active` 的决策做 cosine 相似度。
- **触发条件**：相似度 > 0.78 **且** 提取到的 topic 和决策的 topic 模糊匹配（避免话题撞车）。
- **白话**：每条新消息都跟所有"有效便利贴"过一遍，像不像？像就贴脸提醒。

#### d. Supersede（版本覆盖）—— 让新决策吃掉旧决策

- **流程**：新抽到的决策与旧决策 `topic` 相同但 `statement` 矛盾 → 喂给 LLM 做"二次裁决"（这俩是不是真冲突？）→ 是 → 旧 `status=superseded`，新 `supersedes = old.id`。
- **白话**：群里今天说"改用方案 C 了"，系统会把上周"用方案 B"那张便利贴打个删除线，但不丢——以后还能查"为啥又改了"。
- **降级方案**（赶时间时）：跳过 LLM 二次裁决，纯规则版（topic + 关键词冲突即覆盖），损失约 5% 准确率。

---

## 3. 评测设计（挑战三）：DecisionBench-50

> 评委一定会问："你说你记住了，证据呢？"——所以**先设计指标，再写代码**。

### 3.1 五大指标


| 指标                     | 说人话定义                                | 怎么算                                          | 目标     |
| ---------------------- | ------------------------------------ | -------------------------------------------- | ------ |
| Decision-Recall@5      | 给一句新提问，前 5 条召回里有没有正确答案               | 命中数 / 总测试题数                                  | ≥ 0.85 |
| Repeat-Debate-Block    | 模拟"重提旧争论"，系统能不能主动拦下来                 | 主动弹卡片次数 / 应该拦的次数                             | ≥ 0.75 |
| Forget-Alert-Precision | 复习提醒中，用户点"有用"的比例                     | 用户点 ✅ 的次数 / 推送次数                             | ≥ 0.70 |
| Token-Saved            | 比起朴素 RAG（把整堆历史塞 prompt），我们省了多少 token | 1 - 我们的 prompt token / baseline prompt token | ≥ 40%  |
| Latency                | 用户消息进来 → 卡片弹出来，几秒？                   | p95 端到端延时                                    | ≤ 2.5s |


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

> **角色定义**（按现有代码栈匹配，每人聚焦一块物理代码区，最小化合并冲突）：
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
| B   | 飞书侧：在 `channels/feishu.py` 增加 "决策卡片"模板（标题/理由/反对/结论/时间）；CLI 侧：`nanobot/cli/commands.py` 新增 `claw memory inject --topic=...`                      | `claw memory inject` 可写入 1 条决策；飞书能渲染卡片       | 命令行写入 → 飞书群里 30 秒内出现卡片                     |
| C   | 编写 `docs/bench/decisionbench.jsonl` 前 20 条样例 + 抽取 Prompt v1（`templates/custom/decision_extract.md`）                                             | 20 条标注数据 + Prompt 文件；跑通 A 的抽取得到 baseline 准确率 | 至少 12/20 题抽对（Recall ≥ 0.6）                 |


**Day 3 联调点**：三人凑一起，把 C 的 20 条样本喂给 A 的抽取，B 把结果以卡片形式渲染在飞书 — 这一刻就是 M1 里程碑。

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
4. 全员：在飞书建 "DecisionMind 研发群"，把 bot 拉进去做实时联调环境；约定每日 19:00 5 分钟站会（在飞书视频会议）。

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


