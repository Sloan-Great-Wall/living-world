# Technical Glossary & Architecture Primer

> 项目里反复出现的关键术语、它们各自在干什么、以及彼此如何协作。
> Last updated: 2026-04-15

---

## 1. Core Concepts

### LLM (Large Language Model)
底层"大脑"。输入 prompt 输出 tokens 的**纯函数 (stateless function)**。我们用 Claude 家族：Opus (旗舰), Sonnet (平衡), Haiku (快/便宜)。LLM 本身**没有记忆、没有人格、没有状态**——这些都是外部工程出来的。

### Agent
LLM + tools + memory + persona 的组合体。一个 "agent" = "一个有身份、有目标、能用工具、有记忆的 LLM 调用封装"。在代码里它通常不是常驻进程，而是每次需要时冷启动拼装出来的。

### Persona
Agent 的"人格"。工程上就是一段 **persona card**（身份/立场/说话风格/目标）+ **interview memory**（一段 transcript 作为初始长期记忆）。两种来源：
- **Bio-based** (Smallville 2023) — 一段作者手写的自然语言描述
- **Interview-based** (1000 People 2024) — 2 小时访谈 transcript 作为 memory 灌入，可信度 +85% GSS accuracy

### Prompt
给 LLM 的输入文本。在 agent 系统里通常分段拼装：
```
[system prompt] + [persona card] + [retrieved memories]
              + [world snapshot] + [current user input]
```

### Context Window
LLM 一次能"看到"的最大 token 数（Claude Opus 目前 200K+，1M context 版本专用模型）。**不是免费的**——越长 latency 和 cost 越高，且真正重要的信息会被稀释。这就是为什么需要下面那一堆 memory 和 compaction 技术。

### Token
LLM 处理的最小单位，约等于 0.75 个英文单词或半个中文字。**所有成本都按 token 计费**。Token 消耗 = (input tokens × 单价) + (output tokens × 单价)。

---

## 2. Memory Stack

### Working Memory
当前 context window 里的内容，一次调用结束就消失。

### Episodic Memory
"某个时刻发生了什么"的记忆，通常存在向量数据库 (vector DB) 里。每条 entry 是一段文本 + embedding (向量) + metadata (时间/agent_id/重要性)。查询时按相似度检索出 top-k 条。

### Semantic Memory
抽象知识（"巴黎是法国首都"），和某个具体时刻无关。目前在 agent 产品里用得少，主要还是靠 LLM 预训练知识。

### Reflection
Smallville 提出的关键机制：**周期性地把一堆零碎 episodic memories 压缩成高层 narrative summary**。比如"过去一周 agent 和玩家的 37 次对话"被压缩成"agent 开始信任玩家并把他当成可靠的盟友"。检索时优先捞 reflection，比捞原始事件信噪比高得多。

### Memory Stream
Smallville 的 memory 组织方式：所有记忆（events + reflections + plans）按时间顺序排成一条 stream，检索时综合 **recency / importance / relevance** 三个维度打分。

### Vector Database / Vector DB
专门存 embedding 的数据库，支持按向量相似度查询。常见：Chroma (我们代码里在用)、pgvector、Pinecone、Qdrant、Weaviate。本质就是"给一段查询文本，找出最相关的 top-k 条历史记录"。

### Embedding
把一段文本映射成固定长度的向量（比如 1536 维浮点数），相似语义的文本向量距离近。所有 vector DB 的底层原理。生产上通常用专门的 embedding model (text-embedding-3-small, nomic-embed-text 等)，不用主模型跑 embedding。

### Retrieval / RAG (Retrieval-Augmented Generation)
"查询→捞相关记忆→塞进 prompt 里一起给 LLM" 这套流程。我们每个 tick 每个 agent 都在做这件事。

### Compaction
Claude Agent SDK 内置能力：context 快满时，自动把旧消息总结成一段 summary，然后用 summary 重开 context。避免"context 爆掉"这个 long-running agent 的核心难题。详见 [Anthropic 的 context engineering 文档](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)。

### Memory Tool
Claude Agent SDK 提供的一个 tool：让 Claude 显式把东西写进文件系统，下次 session 读回来。和 compaction 配合使用，解决跨 session 持久化。

---

## 3. Runtime Concepts

### Tick
**一个离散时间步**。simulation 类程序的心跳。Tick 0, Tick 1, Tick 2... 每个 tick 里世界状态会推进一点（每个 agent 做一次决策、物理状态更新、事件派发）。我们 `site-zero` 代码里 `tick_interval_seconds: 1.0` 表示每秒一个 tick。

游戏引擎里叫 frame 或 update cycle，本质一回事，只是粒度不同（游戏一般 60 fps = 16ms/tick，我们 simulation 可以 1s/tick）。

### Tick Loop
**主循环**。代码形态大致是：
```python
tick = 0
while True:
    tick += 1
    perceive_all_agents()
    dispatch_agent_decisions()
    apply_physics()
    write_world_state()
    await asyncio.sleep(interval)
```
这是整个 simulation 的骨架。`site-zero/site_zero/runner.py` 里 `run_simulation` 就是一个 tick loop。

### Phase (相位)
**一个 tick 内部的子步骤**。一个 tick 常被切成几个 phase 依次执行，保证数据一致性。我们系统里可以设计成：

1. **Perception phase** — 每个 agent 看到自己那片世界切片
2. **Recall phase** — 每个 agent 从 vector DB 捞相关记忆
3. **Decision phase** — 每个 agent 调用 LLM 决定做什么
4. **Debate phase (博弈相位)** — 当存在 multi-stakeholder 事件时，涉事 agent 通过 orchestrator 交换立场
5. **Commit phase** — 把决策结果写回 world state
6. **Reflection phase** — (周期性) 压缩记忆成 narrative summary

**"博弈相位"** 特指第 4 步：同一 tick 内，多个 agent 就同一个事件派发意见，由 orchestrator 裁定或汇总。这是我们产品核心玩法所在。

### Cold Start
每次调用 LLM 都重新拼 prompt，不维持常驻 session。Persona 连续性靠**从 vector DB 捞出来的 memory**，不靠"活着的进程"。这是 stateless + scoped memory 的 2026 行业主流做法。

### Stateless / Stateful
- **Stateless** — 每次调用独立，LLM 本身是这样
- **Stateful** — 保留跨调用的状态，通过外部 memory store 实现

---

## 4. Orchestration Layer

### Agent Loop
Claude Agent SDK 的核心抽象。一次循环 = 给 Claude 一个 prompt → Claude 决定用 tool 还是输出 → 执行 tool → 把结果喂回去 → 重复，直到 Claude 认为完成。简单但强大。

### Tool Use
让 LLM 调用外部函数的能力。Claude 会输出结构化 JSON 说"我要调用 `search_memory(query="foo")`"，harness 执行后把结果喂回给 Claude 继续推理。

### Orchestrator / Worker Pattern
Anthropic 多 agent 系统的主架构（[官方博客](https://www.anthropic.com/engineering/multi-agent-research-system)）：一个 **orchestrator (通常是 Opus)** 负责拆任务、派发、汇总；多个 **worker (Sonnet/Haiku)** 并行跑子任务。Worker 之间不直接聊天，消息经 orchestrator 中转，避免 N² 消息风暴。

对比单 Opus，Opus+Sonnet 组合在内部 eval 上 +90.2% 表现，但 token 消耗也高 ~15x——所以**不是所有任务都值得用多 agent**。

### Subagent
被 orchestrator 调用的 worker agent，有自己独立的 context window 和 persona。Claude Code 里通过 `Task` tool 启动 subagent。

### Harness
"跑 agent 的壳"。包含 agent loop、tool 调度、memory 管理、compaction、error recovery、observability。Claude Agent SDK 就是 Anthropic 把 Claude Code 的 harness 剥出来给开发者用。

### LangGraph
LangChain 团队做的 **stateful workflow orchestration framework**。把复杂 agent 工作流表达成 directed graph：
- **Node** — 一个操作（LLM call / tool call / 自定义函数）
- **Edge** — 控制流（可以是 conditional edge，可以 loop）
- **State** — 在节点之间传递的 TypedDict
- **Checkpoint** — 状态自动落盘，崩了能恢复

**你的理解完全对**——就是"BPM 流程图 / 化工流程图 / 企业协作流程图的 LLM 版本"。每个 node 可以是一次 Claude 调用（里面用 Claude Agent SDK），edge 决定下一步去哪个 node。

**License**: Apache 2.0，开源免费。LangChain 生态的商业化产品是 LangSmith (observability) 和 LangGraph Platform (managed hosting)，但核心 framework 本身不要钱。

**何时用 / 何时不用**:
- ✅ 用：复杂分支、循环、有 human-in-the-loop 审批点、需要 checkpoint 恢复
- ❌ 不用：简单线性流程、MVP 阶段、只有一个 tick loop

我们 MVP 不用 LangGraph，纯 asyncio 就够了。等产品长到有复杂 workflow 再迁。

### LangChain
LangGraph 的**前身**和更宽的生态。早期那套"把 LLM 调用串起来的 primitive 库"。现在在 agent 领域主流是 LangGraph 或 Claude Agent SDK，**LangChain 本身的抽象层已经不是首选**。

---

## 5. Framework Landscape

| 框架 | 定位 | 何时选 |
|---|---|---|
| **Claude Agent SDK** | Anthropic 官方 agent harness | 绑 Claude 生态；重 tool use 和 subagent |
| **LangGraph** | Stateful workflow orchestration | 复杂控制流、需要 checkpoint/可视化 |
| **LangChain** | LLM primitive 组合库 (已衰) | 简单 RAG pipeline、legacy 项目 |
| **OpenAI Agents SDK** | OpenAI 官方 agent harness | 绑 OpenAI 生态 |
| **CrewAI** | Role-based multi-agent | 需要清晰 role 定义的协作任务 |
| **AutoGen** | Microsoft 多 agent | 研究用途居多 |
| **Convex AI Town** | 开箱即用 agent 小镇 | 原型 / 教学用，不是生产级 |

**2026 行业共识**：**LangGraph 做骨架 + Claude Agent SDK 做节点内的重活**。但这是成熟期的配置，MVP 阶段 over-engineered。

---

## 6. Three-layer Separation (来自 Anthropic Managed Agents 架构)

这是我们要抄的核心架构范式：

```
┌─────────────────────────────────────┐
│ Brain     (Claude model)            │  ← 只做决策，不做执行
│  - 接收 context，输出决定             │
├─────────────────────────────────────┤
│ Hands     (sandbox runtime)         │  ← 只做执行，不做决策
│  - 跑 tool call, 操作 world state     │
├─────────────────────────────────────┤
│ Orchestration (harness)             │  ← 管 context 拼装 / retry / checkpoint
│  - 何时调 brain, context 怎么组装     │
└─────────────────────────────────────┘
```

三层分开的好处：brain 可换模型（Opus → Sonnet → Haiku）；hands 可换 sandbox；orchestration 可换 framework。

---

## 7. Architecture Overview (我们的产品)

```
                    ┌──────────────────────────┐
                    │   World State            │
                    │   Redis + pgvector +     │
                    │   event log              │
                    └────────────┬─────────────┘
                                 │
     ┌───────────────────────────┼──────────────────────────┐
     │                           │                          │
┌────▼─────┐              ┌──────▼──────┐            ┌─────▼──────┐
│Tick Loop │              │  Scenario   │            │  Memory    │
│(asyncio) │◄────────────►│  Engine     │◄──────────►│  Layer     │
│          │              │  event /    │            │  pgvector  │
│          │              │  debate     │            │  + Claude  │
└────┬─────┘              └─────────────┘            │  memory    │
     │                                                │  tool      │
     │ per tick                                       └─────┬──────┘
     │ 冷启动每个受影响 agent                                │
     ▼                                                     │
┌──────────────────────────────────────────┐    retrieve  │
│     Claude Agent SDK Runtime              │◄────────────┘
│  ┌──────────┐  ┌────────┐  ┌──────────┐   │
│  │Orchestra-│  │ Worker │  │ Worker   │   │
│  │tor (Opus)│  │(Sonnet)│  │ (Haiku)  │   │
│  └──────────┘  └────────┘  └──────────┘   │
│     汇总           深度推理      日常 tick      │
└──────────────────────────────────────────┘
     │
     ▼
┌─────────────────────┐
│  Presentation       │
│  Unity + Mapbox     │
│  (LBS client)       │
└─────────────────────┘
```

### 固定的 Prompt Composition (五段式)

每次调用 Claude 之前，context 按固定模板拼装：

```
1. persona_card         — 该 agent 的身份与立场 (短，固定)
2. world_snapshot       — 当前地点 / 时间 / 附近其他 agent
3. retrieved_reflections — 从 vector DB 捞的高层 narrative summary
4. recent_raw_events    — 最近 N 个原始事件 (短期 working context)
5. current_prompt       — 本次调用要 agent 做什么
```

每段独立控长度预算，按需裁剪。这是 [Anthropic context engineering 指南](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 推荐的做法。

---

## 8. Tiered Tick Strategy (成本控制的关键)

```
Dormant tier (90%+ agents, 玩家远处)
  └── 纯 stat machine, 零 LLM call
      (借鉴鬼谷八荒 / 太吾绘卷的 event table)

Awake tier  (玩家附近或剧情相关)
  └── Haiku, 简短对话 + 小事件
      tick 频率：每 5-30 分钟

Spotlight tier (关键剧情节点)
  └── Sonnet/Opus, 完整 5 段式 prompt
      频率：按事件触发, 非固定
```

这是把 MVP 成本从"天文数字"压到"可持续"的根本。没有这层分级的多 agent 产品基本都活不下来。

---

## 9. Key References

- [Generative Agents: Interactive Simulacra (Park et al. 2023)](https://arxiv.org/abs/2304.03442)
- [Generative Agent Simulations of 1000 People (Park et al. 2024)](https://arxiv.org/abs/2411.10109)
- [genagents GitHub — Stanford HCI](https://github.com/joonspk-research/genagents)
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [How we built our multi-agent research system — Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Memory tool — Claude API docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [Niantic Large Geospatial Model](https://nianticlabs.com/news/largegeospatialmodel)
