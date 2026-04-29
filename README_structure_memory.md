# 结构化决策记忆（Decision Layer）交付说明

本文档说明本次将 **`DecisionMemoryStore`** 接入 Nanobot 分层记忆主线的改动范围、运行时行为与验收方式，便于提交 Git / Code Review。

---

## 1. 目标

在保持原有 **短期窗口（Shorterm）→ 情景检索（Episodic / LightRAG）** 的前提下，增加：

1. **写入**：会话窗口触发卸批（≥1000 条可见历史并触发 `_is_rebuild`）时，对卸下的消息批次做 **`extract` → `store`**，写入 **`memory/decisions.db`**，并在 **`EpisodicMemoryStore._rag`** 已初始化时向 LightRAG **`ainsert`** 决策文本块（双写）。
2. **读出**：拼装 system prompt 时，按 **`channel:chat_id`**（与 `Session.key` 一致）注入 **本会话已落库的决策摘要**；**`efficient()`** 在「有 RAG **或** 有决策行」时为真，避免仅有决策但无 `rag_storage` 时整段 Memory 被挡掉。

---

## 2. 涉及文件

| 文件 | 变更摘要 |
|------|----------|
| `nanobot/agent/loop.py` | 当 `provider` 为 **`OpenAICompatProvider`** 时构造 **`DecisionMemoryStore`**，注入 **`ContextBuilder`** 与 **`ShortermMemoryStore`**；对外保留 **`self.decision_store`**（非兼容 Provider 时为 `None`）。 |
| `nanobot/agent/context.py` | `ContextBuilder` 接受 **`decision_store`**；**`build_system_prompt`** 增加 **`chat_id`**，计算 **`memory_project = f"{channel}:{chat_id}"`** 并传入 **`aggregation_memory` / `efficient`**。 |
| `nanobot/agent/hiarch_memory/memory.py` | **`HiarchMemoryStore`** 支持 **`decision_store`**；**`aggregation_memory(..., memory_project=)`** 拼接 Episodic 检索与决策块；**`efficient(..., memory_project=)`** 综合 RAG 与决策表。 |
| `nanobot/agent/hiarch_memory/shorterm.py` | 卸批后 **`extract` + `store`**；缺省不启用的场景为 **`decision_store is None`**。 |
| `nanobot/agent/hiarch_memory/decision.py` | 已有 **`has_for_project(project)`**（供 `efficient` 使用）。 |
| `analysis/memory-flows.md` | 与实现同步的说明（见该文档 **§6**）。 |

未改：Episodic 的 `InterMediate` 抽取链、传统 `MemoryStore` / Dream 仍保持原状。

---

## 3. 运行时数据流（集成后）

1. **`AgentLoop._process_message`** → **`ShortermMemoryStore.rebuild_history(session)`**  
   - 若窗口满：卸下 **`batch`** → `_save_history` → **`DecisionMemoryStore.extract(batch, project=session.key)`** → 若有结果则 **`store`**。  
   - 随后逻辑不变：Episodic **`check()`**、清理 `.history.jsonl`、写 `.shortermem.jsonl`。

2. **`ContextBuilder.build_messages`** → **`build_system_prompt(..., channel=, chat_id=)`**  
   - **`HiarchMemoryStore.aggregation_memory(current_message, memory_project="channel:chat_id")`**  
   - 拼接：**LightRAG 检索文本**（若有） + **`list_by_project` 渲染的决策块**（若有）。

3. **`efficient(memory_project=)`**  
   - `EpisodicMemoryStore.can_retrieve()` **或** `DecisionMemoryStore.has_for_project(memory_project)` 为真则注入 **`# Memory`**。

---

## 4. 约束与限制

- **Provider**：结构化抽取依赖 **`OpenAICompatProvider.chat_scheme`**（与 Episodic 相同）。**Anthropic-only 等非兼容 Provider** 下 **`decision_store` 为 `None`**，决策能力关闭，其余记忆不受影响。
- **触发频率**：决策抽取仅在 **卸批**（默认历史长度 ≥1000）时触发；日常短会话不会在每次请求抽决策（与 proposal 一致，避免刷屏调用）。
- **Neo4j / LightRAG**：若 Episodic 未成功初始化 **`_rag`**，决策仍会写入 **SQLite**；RAG 双写在该次 `store` 中跳过。

---

## 5. 如何自测

1. 依赖与单测（不连外网 LLM 时仍可通过 Mock 测 store）：

   ```bash
   uv sync --group dev
   uv run pytest tests/test_decision_extract.py -v
   ```

2. 手工：使用 **OpenAI 兼容** 的 Provider 跑网关/CLI，使某 `session` 历史触达卸批条件，然后检查工作区：

   - `memory/decisions.db` 是否出现新行（`project` 列应对应 `channel:chat_id`）；  
   - 下一任 user 轮 system 中是否出现 **「Recorded decisions」** 段落（在 **# Memory** 下）。

3. 可在运行中的 **`AgentLoop` 上读 `agent.decision_store is not None`** 快速确认当前进程是否启用了决策层。

---

## 6. 参考

- 全链路细节与图示：`analysis/memory-flows.md`（**§6 结构化决策记忆**）。  
- 产品级 Router / 复习 Cron / 飞书卡片等见 `analysis/proposal.md`（后续 Sprint）。
