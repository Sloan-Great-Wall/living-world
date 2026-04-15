# Core Flow Loops

> 产品运行时的四张关键流程图，从宏观到微观。
> Last updated: 2026-04-15

这四张图不是 LangGraph 语法，是**概念级 flow diagram**。MVP 用 plain `asyncio` 写死即可，等复杂度上来再迁 LangGraph。

---

## Flow 1: Player Session Loop (玩家会话层)

玩家打开 app 到关闭的单次会话。

```
玩家打开 app
   │
   ▼
GPS + VPS / 退化 GPS 定位
   │
   ▼
拉取附近 tile 的 active agent list
   │ (按 agent 的 tier 拉取: dormant 摘要 + awake 全量)
   ▼
渲染 AR / map 视图
   │
   ▼
┌──────────────────────────────────────┐
│ 玩家交互循环 (长时驻留)                │
│                                        │
│  检测玩家进入 agent 视野               │
│   → agent 进入 awake tier              │
│   → agent 主动打招呼 (如有 memory)     │
│                                        │
│  玩家对话 / 给道具 / 委托任务 / 旁观   │
│   → 触发 Agent Decision (Flow 3)       │
│   → 可能触发 Debate Phase (Flow 4)     │
│                                        │
│  世界事件推送 (spotlight event 通知)    │
│  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │
└──────────────────────────────────────┘
   │
   ▼
玩家退出
   │
   ▼
持久化玩家状态 (位置, 关系快照, 未读事件)
   │
   ▼
附近 agent 降级回 dormant tier
```

---

## Flow 2: World Tick Loop (世界自转层)

整个世界的心跳，7×24 运行在服务端。

```
每秒一次 scheduler 唤醒
   │
   ├── Dormant tier tick (5-30 min 频率)
   │      │
   │      ▼
   │   批量读取所有 dormant agent
   │      │
   │      ▼
   │   执行 stat machine 规则
   │   (属性缓变 + 事件表掷骰 + 关系衰减)
   │      │
   │      ▼
   │   批量写回 world state
   │
   ├── Awake tier tick (玩家附近触发, 频率随玩家密度)
   │      │
   │      ▼
   │   for each awake agent:
   │      Perception → Recall → Decision (Haiku) → Commit
   │      (这是 Flow 3 的单次执行)
   │
   ├── Spotlight event trigger?
   │      │ yes
   │      ▼
   │   启动 Debate Phase (Flow 4)
   │
   └── Reflection tick (每日低峰时段)
          │
          ▼
       for each agent with enough new events:
          读取过去 24h raw events
             │
             ▼
          Sonnet 压缩成 narrative summary
             │
             ▼
          写入 reflection table, 提升检索优先级
```

---

## Flow 3: Agent Decision Graph (单个 agent 单次决策)

每次 agent "动一下"的内部流程。这是系统里调用最频繁的循环。

```
   输入: current_event
   (玩家对话 / 邻居事件 / 内部状态变化)
        │
        ▼
   load persona_card (agent_id)
        │
        ▼
   retrieve_reflections (vector DB, top-k)
   ─ 捞该 agent 过去的高层 narrative
        │
        ▼
   retrieve_recent_events (timeline, 最近 N 条)
   ─ 短期 working memory
        │
        ▼
   build_world_snapshot
   ─ 所在 tile 信息 / 时间 / 附近 agent / 活跃事件
        │
        ▼
   五段式 prompt composition
   [persona_card | world_snapshot |
    retrieved_reflections | recent_events |
    current_prompt]
        │
        ▼
   model routing
   ┌─ 日常对话 / 小决定 → Haiku
   ├─ 复杂推理 / 长对话 → Sonnet
   └─ 关键剧情节点 → Opus
        │
        ▼
   call Claude
        │
        ▼
   ┌─ needs tool? ─────┐
   │ yes                │ no
   ▼                    ▼
 execute tool        commit decision
 (read memory,            │
  search, RAG...)         ▼
   │                 write to world state
   ▼ (loop)               │
   回 call Claude           ▼
                     remember (写 memory + embedding)
                           │
                           ▼
                     trigger stat machine updates
                     (好感度 / 属性 / 道具)
```

---

## Flow 4: Debate Phase Graph (博弈相位 — 核心玩法)

多方利益 agent 就同一事件发表立场并汇总。这是我们产品**区别于普通 NPC 对话**的核心。

```
事件触发
(玩家做出选择 / NPC 主动引爆事件 /
 世界级 spotlight event)
        │
        ▼
Orchestrator (Opus) 接收事件
        │
        ▼
识别利益相关方 (stakeholders)
 ─ 从 world state 拉"对此事件有立场"的 agent
 ─ 按相关性打分, 选 top-N (通常 3-7 个)
        │
        ▼
为每个 stakeholder 生成 debate brief
 (事件描述 + 该 agent 的既有立场 + 可能的冲突点)
        │
        ▼
   ┌──────────────────────┐
   │ 并发派发 (asyncio.gather) │
   │                        │
   │   Agent A (Sonnet)     │──┐
   │   Agent B (Sonnet)     │──┤
   │   Agent C (Sonnet)     │──┤  每个 worker 带自己
   │   Agent D (Sonnet)     │──┤  persona + retrieved memory
   │   ...                  │──┤  输出: 立场 + 理由 + 情感
   └──────────────────────┘──┘
        │
        ▼
Orchestrator 汇总
 ─ 识别共识 / 冲突点 / 极端立场
 ─ 裁定事件走向 (或留悬念交给玩家下一步)
        │
        ▼
生成叙事报告 (给玩家)
 + 写回每个参与 agent 的 memory
 + 更新 agent 之间的关系图 (好感度, 仇恨值...)
 + 可能触发后续 spotlight event (连环事件)
        │
        ▼
推送给玩家 (如在线) 或存为"回来时展示"
```

### Debate Phase 的设计要点

1. **Stakeholder 选择**是关键：选少了没张力，选多了成本爆炸。**3-7 个是 sweet spot**
2. **Worker 之间不直接对话**：全部经 orchestrator 中转，避免 N² 消息风暴 (Anthropic 官方推荐)
3. **每个 worker 只发言一轮**：不做多轮 debate，成本太高。想要多轮可以拆成多个 tick
4. **Orchestrator 的裁定不是"选一个立场赢"**：而是"描述事件在这些立场影响下走向了 X"
5. **失败降级**：worker 超时 → 用 persona_card 规则默认立场代替

---

## 这些 Loop 在代码里的对应

| Flow | 现有 `site-zero` 代码 | 缺口 |
|---|---|---|
| Flow 1 | 无 (需新建 client 层) | 完全缺失 |
| Flow 2 | [runner.py](../site-zero/site_zero/runner.py) 的 tick loop | 缺 tier 分级、缺 scheduler |
| Flow 3 | `apply_scp173_tick_async` 等函数 | 架构已有雏形, 差 model routing |
| Flow 4 | 完全缺失 | 最关键的新增模块 |
