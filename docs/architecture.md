# System Architecture Overview

> 截至 2026-04-15 讨论确定的整体架构及其设计原理。
> 这份文档是 [product-direction.md](product-direction.md), [tech-glossary.md](tech-glossary.md), [flow-loops.md](flow-loops.md), [stat-machine-design.md](stat-machine-design.md) 的综合视图。

---

## 0. 一句话概括

**一个由 stat machine 驱动、由分层 LLM 加持、以 world pack 组织内容、以真实地理位置锚定的 living world simulator, 玩家通过 DnD 跑团风格交互进入并影响这个世界。**

---

## 1. 设计原则 (架构背后的"为什么")

这五条原则决定了所有下游技术选择:

### 原则 1: LLM 是加层, 不是基底
世界的"活着"不依赖 LLM 能不能用。Tier 1 (纯 Python 规则) 必须独立能跑出有戏剧感的 legend log。LLM 只负责"让同样的事件读起来更生动"。这保证了成本可控 + 不被单一供应商锁死。

### 原则 2: Stateless LLM + Scoped Memory
所有 agent 的"持久人格"不靠常驻进程,靠**每次 cold-start 时从向量数据库检索该 agent 的记忆**。LLM 本身始终是 stateless 函数。这是 2026 工业共识。

### 原则 3: 分层按重要度调用
不是所有事件都值得花同样的钱。用 **importance scoring** 把事件分给三层 (固定规则 / 本地小模型 / 在线大模型), 90%+ 流量走 Tier 1。

### 原则 4: World Pack 解耦
世界观不是硬编码在代码里, 是数据驱动的可插拔模块。一个 pack 自带 persona 池 + 事件表 + storyteller 人格。可单独运行也可叠加运行。

### 原则 5: 先文字后 AR
DnD 跑团式文字体验是产品灵魂。AR/LBS 是交付形态, 是包装。如果在 web 文字版都不好玩, AR 拯救不了。

---

## 2. 分层架构全貌

```
┌─────────────────────────────────────────────────────────┐
│ L7  Presentation Layer                                   │
│  ├─ Stage A: 内部 Web Dashboard (Next.js)                │
│  ├─ Stage B: 玩家 Web 客户端 (文字跑团 UI + 骰子)         │
│  ├─ Stage C: iOS/Android 原生 app (高德 SDK + ARKit)     │
│  └─ Stage D: AR + 收集/对战/社交功能                      │
└────────────────────┬────────────────────────────────────┘
                     │ REST / WebSocket
┌────────────────────▼────────────────────────────────────┐
│ L6  API Gateway                                          │
│  ├─ 鉴权 (手机号 + 实名制)                                 │
│  ├─ 限流 (per-user Tier 3 budget)                         │
│  └─ 反作弊 (Stage C+ 的 GPS 伪造检测)                     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ L5  Orchestration Layer                                  │
│  Tick Loop (asyncio) — 驱动整个世界心跳                   │
│  ├─ Player Session Loop    (Flow 1)                      │
│  ├─ World Tick Loop        (Flow 2)                      │
│  ├─ Agent Decision Graph   (Flow 3, 每个 agent 冷启动)    │
│  └─ Debate Phase           (Flow 4, 多 agent 并发博弈)    │
│                                                          │
│  MVP 用 plain asyncio; 复杂度上来后迁移 LangGraph         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ L4  Decision Engine (三层 stat machine)                  │
│                                                          │
│  ┌────────────────────────────────────────────────┐     │
│  │ Tier 3: 在线强力模型 (云 API)                     │     │
│  │  DeepSeek V3 (主力) / Qwen-Max (备份)           │     │
│  │  Kimi (长 context 专用)                         │     │
│  │  Spotlight + Debate Phase + Reflection          │     │
│  │  importance ≥ 0.6, ~ ¥0.05-1 / call             │     │
│  └──────────────────┬─────────────────────────────┘     │
│                     ▲                                    │
│                   升级                                   │
│                     │                                    │
│  ┌──────────────────┴─────────────────────────────┐     │
│  │ Tier 2: 本地小模型 (自托管)                       │     │
│  │  Qwen2.5-7B / DeepSeek-V2-Lite                  │     │
│  │  Legend 润色 + 路人对话                          │     │
│  │  importance 0.2-0.6, ~ ¥0.001 / call            │     │
│  └──────────────────┬─────────────────────────────┘     │
│                     ▲                                    │
│                   升级                                   │
│                     │                                    │
│  ┌──────────────────┴─────────────────────────────┐     │
│  │ Tier 1: 固定规则 (纯 Python, 零成本)              │     │
│  │  ├─ AI Storyteller (RimWorld 风, tile 级节奏)     │     │
│  │  ├─ Agent Stat Machine (太吾/鬼谷风, 属性+事件)    │     │
│  │  └─ Historical Figure Registry (DF 风, 分级模拟)  │     │
│  │  importance < 0.2, 95%+ 流量                     │     │
│  └─────────────────────────────────────────────────┘    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ L3  World State Layer                                    │
│  ├─ PostgreSQL (agents / tiles / events / relationships) │
│  ├─ pgvector (per-agent episodic memory embeddings)      │
│  ├─ Redis (热数据: 当前 tick / awake agent 缓存)          │
│  └─ Event Log (append-only, CQRS 风格)                   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ L2  World Pack Layer (数据驱动, 内容可插拔)                │
│  world_packs/                                            │
│    ├─ scp/       (persona + 事件表 + storyteller + tile) │
│    ├─ cthulhu/   (同上)                                   │
│    ├─ liaozhai/  (同上)                                   │
│    └─ cross_pack_events.yaml (可选: 跨 pack 交织事件)     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ L1  Infrastructure                                       │
│  ├─ Geography: 高德 SDK + GCJ-02 坐标系 + H3 tile         │
│  ├─ LLM Providers: DeepSeek / Qwen / Kimi / 百炼          │
│  ├─ Self-hosted: vLLM (Qwen2.5-7B) on 4×A10              │
│  ├─ Embedding: BGE-M3 (自托管) or 百炼 API               │
│  └─ Observability: Prometheus + Grafana + OpenTelemetry  │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 数据流: 一个事件从产生到玩家看见的完整路径

以"玩家 A 在 wujin-lane tile 遇到聊斋女鬼聂小倩, 询问她的身世"为例:

```
1. [L1] 玩家 GPS 定位到 H3 cell X
         │
2. [L2] 查询 cell X 绑定的 tile = wujin-lane (来自 liaozhai pack)
         │
3. [L3] 读取 wujin-lane tile 内的 active agents
         └─ 命中 Nie-Xiaoqian (historical figure, liaozhai pack)
         │
4. [L5] 玩家发起对话 → 触发 Agent Decision Graph (Flow 3)
         │
5. [L4] importance scoring:
         ├─ historical figure: +0.3
         ├─ player-touched: +0.4
         └─ 总分 0.7 → Tier 3
         │
6. [L3] 为 Nie-Xiaoqian 拼 5 段 context:
         ├─ persona_card (固定)
         ├─ world_snapshot (wujin-lane 当前状态 + 旁边谁在)
         ├─ retrieved_reflections (pgvector 检索 top-6)
         ├─ recent_raw_events (最近 10 条)
         └─ current_prompt (玩家的话)
         │
7. [L4 Tier 3] 调 DeepSeek V3, 玩家看到 Nie-Xiaoqian 的回复
         │
8. [L3] Write memory:
         ├─ 本次对话 embed 进 pgvector
         ├─ 玩家-Xiaoqian 关系好感度 +N
         └─ wujin-lane 事件 log append 一条
         │
9. [L4 Tier 1] 触发后续 stat machine updates:
         └─ Xiaoqian 的 "被知晓身世" 属性 +1 (可能影响未来事件)
         │
10.[L7] 返回玩家 UI, 骰子动画 + 回复文字 + 关系变化提示
```

全链路用时预期 **3-8 秒** (主要是 Tier 3 的延迟), 玩家端有骰子动画和"思索中..."填充等待感。

---

## 4. 三个关键子系统的原理

### 4.1 Memory 子系统

**问题**: LLM 是 stateless 的, 怎么让 agent "记得" 玩家和其他 agent?

**原理**: 分三层时间尺度存储:

| 层 | 存储 | 时间尺度 | 检索方式 |
|---|---|---|---|
| **Raw Events** | PostgreSQL event log | 小时-天 | 时间倒序 top-N |
| **Episodic Embeddings** | pgvector, per-agent | 周-月 | 语义相似度 top-K |
| **Reflections** | pgvector, per-agent (高优先级 flag) | 月-年 | 优先被检索 |
| **Persona Card** | 静态文件 | 永久 | 每次都带 |

每次 Tier 2/3 调用前, 按 "5 段式 context composition" 从这四层各取一部分拼成 prompt。

**为什么分层**: 近期原始事件信噪比高但量大, 必须压缩成 reflection。Reflection 是 Stanford Smallville 的核心创新——把"过去一周发生的 37 件事"压缩成"这个 agent 开始信任玩家"。

### 4.2 Decision Routing (三层调用)

**问题**: 如何保证 95% 流量走零成本路径?

**原理**: 每个待处理事件先算 **importance score** (0-1), 按阈值分流:

```
score = 参与者权重 + 事件类型权重 + 关系网影响 + 玩家在场加分
     0.7 ─────────── Tier 3 (在线大模型)
     0.2 ─────────── Tier 2 (本地小模型)
     0.0 ─────────── Tier 1 (纯规则)
```

**关键**: 阈值不是写死的, 而是**受日预算动态调整**。今日 Tier 3 预算用掉 80% → 阈值自动上调到 0.75, 减少触发量。这个机制让单日成本有硬上限。

### 4.3 World Pack 插件机制

**问题**: 如何让 SCP / 克苏鲁 / 聊斋 既能独立又能混合?

**原理**: 每个 pack 是一个自包含目录:

```
world_packs/liaozhai/
├── pack.yaml              # 元信息: 名称/调性/storyteller 人格
├── personas/              # 角色档案 (YAML + 可选 interview transcript)
│   ├── nie-xiaoqian.yaml
│   ├── ying-ning.yaml
│   └── ...
├── events/                # 事件表
│   ├── daily.yaml         # 日常事件
│   ├── spotlight.yaml     # spotlight 事件
│   └── relationships.yaml # 关系驱动事件
├── tiles/                 # 场景类型
│   └── tile_types.yaml    # "市井", "书斋", "荒野" 等
├── storyteller.yaml       # 该 pack 的 AI Storyteller 配置
└── prompts/               # pack-specific prompt 模板
    └── narration.md       # 聊斋调性的叙述模板
```

启动时按 `--packs scp,cthulhu,liaozhai` 加载。每个 agent 的 `pack_id` 字段标记归属, tile 有可选 `preferred_packs` 字段控制"哪个 pack 的 agent 倾向住在这里"。

**Cross-pack** 在独立文件 `cross_pack_events.yaml` 定义, 只在多 pack 启动时激活。这个设计让**任一 pack 都可以独立跑通 Stage A**——纯聊斋世界可以跑, 纯 SCP 世界可以跑, 也可以三个混合跑。

---

## 5. 关键技术选型及理由

| 选型 | 选它的理由 | 备胎 |
|---|---|---|
| **DeepSeek V3** (Tier 3 主力) | 国内最强综合性价比, 2026 价格 ¥2-4/1M tokens | Qwen-Max (贵 5x 但稳定) |
| **Qwen2.5-7B** (Tier 2) | 国内 SOTA 小模型, 中文强, 开源可自托管 | DeepSeek-V2-Lite (MoE 稍贵但效果稍强) |
| **PostgreSQL + pgvector** | 关系型 + 向量一体, 事务一致性 | 分开用 PG + Chroma/Pinecone (复杂且贵) |
| **Redis** (热数据) | 毫秒级读写, 成熟 | KeyDB (开源 fork, 改天再换) |
| **vLLM** (Tier 2 自托管) | 吞吐最强, 生产级 | SGLang / TGI |
| **BGE-M3** (embedding) | 中英双语 SOTA, 开源 | 百炼 text-embedding-v3 (按量付费) |
| **高德地图** | 国内覆盖 + 开发文档友好 + SDK 齐全 | 腾讯地图 (更好集成微信) |
| **ARKit** (iOS) | 国内 iOS 唯一选择, 稳定 | - |
| **ARCore China** | 华为/小米/OPPO/vivo 原生集成 | - |
| **Plain asyncio** (MVP) | 够用, 不欠技术债 | LangGraph (Stage C+ 再考虑) |
| **Next.js** (dashboard) | 前端生态成熟, SSR/SSG 都好 | 纯 React SPA (功能够但 SSR 弱) |

---

## 6. 为什么不选这些 (常见问题)

### 为什么不用 Claude
**不能在中国合规使用**。Anthropic 未在中国设立服务, 且直接调用 api.anthropic.com 涉及数据出境。即便技术上可行, 合规审查过不了。所有 Tier 3 能力由国产大模型承担。架构本身是"LLM 无关"的, 接入哪家只是换 adapter。

### 为什么不用 LangChain/LangGraph
MVP 阶段的控制流足够简单, asyncio 几十行就能写完。LangGraph 的价值在**复杂分支+checkpoint 恢复**, 我们 Stage C 之后再评估是否需要。过早引入 = 技术债 + 黑盒。

### 为什么不一开始就做 AR
AR 是**交付形态**, 不是**产品核心**。Stage A (模拟器) 没跑通时做 AR 是浪费钱。Dwarf Fortress / 太吾绘卷都是纯文字/低视觉就好玩——**好世界不靠画面**。

### 为什么不用 Unity 跨平台一次性做 iOS + Android
Unity 对 ARKit/ARCore 的打磨始终落后原生。我们的 AR 体验要求高, iOS-first 原生开发更靠谱。Android 作为 Stage C 第二批上, 可以评估 Unity 还是双原生。

### 为什么不直接让 LLM 模拟整个世界, 省掉 Tier 1
**成本**。10 万 DAU × 30 分钟/天 × 每 agent 每 tick 一次 LLM call = 单日 $$$$$$$$$ 量级。无论多便宜的模型, 这个量级都不可持续。**"LLM 无关的世界自转" 是必须的。**

### 为什么不用 Smallville 的直接实现
Smallville 有两个缺陷对我们产品致命: (1) **25 agent 规模**, 我们要 1500+; (2) **纯 LLM 驱动**, 成本架构不可持续。我们保留 Smallville 的思想 (memory stream + reflection + planning), 但架构完全重新设计。

---

## 7. 现有代码与目标架构的 gap

现有 `site-zero` 代码目前的状态:

| 组件 | 现状 | 目标 |
|---|---|---|
| Tick loop | ✅ 有 (`runner.py`) | 需要重构为 L5 Orchestration 层, 分 phase |
| Agent perception | ✅ 有 (`perception_pov.py`) | 可复用 |
| Memory (vector) | ⚠️ Chroma | 迁移到 pgvector |
| LLM adapter | ⚠️ Ollama | 抽象成 Tier 2/3 adapter, Ollama 作为 Tier 2 选项 |
| World layout | ⚠️ 硬编码房间图 | 迁移到 H3 tile + pack 内 tile 配置 |
| Entities | ⚠️ 写死 SCP roster | 迁移到 `world_packs/scp/personas/` |
| SCP tick logic | ⚠️ 部分硬编码 | 迁移到 pack 内事件表 + Tier 1 stat machine |
| Storyteller | ❌ 没有 | 新建 |
| Historical Figures | ❌ 没有 | 新建 |
| 3-tier routing | ❌ 没有 | 新建 |
| Debate Phase | ❌ 没有 | 新建 |
| Player | ❌ 没有 | Stage B 开始引入 |

**大部分现有代码可以作为重构基础**, 但核心架构需要"把 SCP 特化代码抽象成 pack + 插入 Tier/Storyteller 层"。这是 Stage A.0 的主要工作。

---

## 8. 小结: 这个架构为什么站得住

三个核心保证:

1. **成本**: Tier 1 cover 95% 流量 + Tier 3 日预算硬上限 → 单用户月成本 ≤ ¥30
2. **扩展性**: World pack 插件化 → 加一个新 IP 不需要改核心代码
3. **抗风险**: Tier 3 全挂了 Tier 2 顶; Tier 2 全挂了 Tier 1 顶; 世界永远自转

这三条合起来的意思是: **我们选择了一个在最坏情况下也能交付基础体验的架构, 在最好情况下能交付惊艳体验**。这种"带降级策略的分层设计"是所有长期能活的大规模系统的共同特征, 无论它是 CDN、数据库, 还是现在的 AI living world。
