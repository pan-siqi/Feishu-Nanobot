# Sprint1/Sprint2 Memory & Channel 状态报告（实施后）

## 1. 报告范围
- 依据 `analysis/proposalV3.md` 中结构框图与 Sprint 目标评估实现状态。
- 范围聚焦：Memory 主链（extract/store/recall/decay/supersede/review）与 Channel 复习闭环（cron 提醒 + 用户回写）。
- 本报告包含“已完成代码改造”与“剩余联调事项”。

## 2. 与结构框图的一致性结论
- 主链路已对齐：`ShortermMemoryStore` 卸批后触发 `DecisionMemoryStore.extract/store`，并在 `ContextBuilder` 注入记忆块。
- 分层记忆可运行：Short-Term + Episodic + Decision 已联通；Working/Semantic 仍为占位（符合当前阶段规划）。
- 路由能力从“固定列表注入”升级为“query-aware decision recall + episodic retrieve”并行注入。

## 3. Sprint 完成度评估（当前）

### Sprint1（Day1-3）
- **Memory：约 90%**
  - 已有：Decision schema、extract、SQLite 持久化、基础测试。
  - 本轮补充：同 topic 去重与 supersede 规则，减少重复决策卡。
- **Channel：约 80%**
  - 已有：Feishu 通道与卡片消息能力。
  - 本轮补充：`/decision-review` 文本回写协议（跨 channel 通用，Feishu 可直接使用）。

### Sprint2（Day4-6）
- **Memory：约 80-85%**
  - 本轮新增：`recall`、`decay`、`list_review_candidates`、`mark_review`、supersede 生命周期行为。
  - 尚缺：基于线上指标的参数调优（Recall@5、误提醒率）。
- **Channel：约 65-75%**
  - 本轮新增：decision review cron 分支 + review 消息生成 + 用户动作回写路径。
  - 尚缺：Feishu 按钮事件直连回写（当前先用文本命令协议保障闭环）。

## 4. 本轮已完成改造（代码落点）
- `nanobot/agent/hiarch_memory/decision.py`
  - 新增 recall 评分与排序。
  - 新增 supersede/去重写入策略。
  - 新增 decay、review 候选筛选、review 动作回写（reinforce/expire/update）。
  - 新增项目枚举能力。
- `nanobot/agent/hiarch_memory/memory.py`
  - 从固定 `list_by_project` 注入改为 query-aware recall 注入。
- `nanobot/agent/context.py`
  - 增加记忆注入长度保护（截断上限）以降低 prompt 膨胀风险。
- `nanobot/cron/decision_review.py`（新增）
  - 复习候选选择与标准化复习消息渲染。
- `nanobot/cli/commands.py`
  - 在 cron 回调增加 `decision_review` 分支，支持 `project=` 与 `limit=` 参数。
- `nanobot/command/builtin.py`
  - 新增 `/decision-review` 命令，用于用户回写决策状态。
- `tests/test_decision_lifecycle.py`（新增）
  - 覆盖 supersede、recall、decay、review action 生命周期行为。

## 5. 闭环能力现状
- **已闭环**
  - 决策抽取 -> 入库 -> 查询召回 -> prompt 注入 -> 定时复习提醒 -> 用户动作回写。
- **当前协议**
  - cron 任务消息示例：`decision_review project=feishu:oc_xxx limit=3`
  - 用户回写命令：
    - `/decision-review <id> reinforce`
    - `/decision-review <id> expire`
    - `/decision-review <id> update <new statement>`
- **待增强**
  - Feishu 按钮事件到 `mark_review` 的直接映射（可作为下一轮 UX 增强）。

## 6. 测试结果
- 命令：`uv run pytest -q tests/test_decision_extract.py tests/test_decision_lifecycle.py`
- 结果：`8 passed`

## 7. 风险与后续联调建议
- 评分权重目前为启发式参数，建议用 DecisionBench 数据做离线回放调参。
- `decay` 半衰期与候选阈值需根据真实团队消息频率调整。
- 当项目规模增大时，建议补充 recall 的 SQL 预过滤与分页策略。
- 下一步优先级：
  1. 接入真实飞书群联调（多会话 project key 隔离验证）。
  2. 采样 Recall@5 与 Supersede Accuracy。
  3. 再决定是否引入按钮回写与 richer card UX。
