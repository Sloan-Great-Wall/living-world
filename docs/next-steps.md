# Stage A MVP — Non-blocking Work Streams

> **唯一目标**: 无玩家、非 VR、自动运行的虚拟世界模拟器。
> 跑 100 虚拟日, 产出 500+ legend events, 团队读 digest 像读章回体小说。
> Last updated: 2026-04-15

---

## 出口标准 (Stage A Exit Criteria)

满足全部 4 条才算 MVP 完成:

- ✅ 世界无人值守连续跑 **100 虚拟日** 不崩
- ✅ 日均产出 **500+ legend events**, 其中 20+ spotlight 级
- ✅ 团队非开发成员读一周 digest, 能记住 10+ NPC 的故事
- ✅ **Tier 1 占总调用 ≥ 95%**, Tier 3 日花费 < ¥200

---

## 工作分 6 条并行线, 全部今天可开工

```
    ┌─ S1 Infra 重构 ───┐
    ├─ S2 内容生产 ─────┼──┐
    ├─ S3 LLM 选型 ─────┘  │
    │                      ├──→ S4 Stat Machine 原型 ──→ S6 Dashboard
    │                      │
    ├─ S5 Observability ──┘
    │
    └─ (S6 Dashboard 晚 2 周启动即可)
```

每条线里的任务按顺序执行, 但**不同线之间**可以完全并行。

---

## S1 · Infra 重构 (后端工程师 × 1-2)

从现有 `site-zero` 开始, 改造为可承载多 world pack 的基础设施。**不依赖任何外部决策, 今天可开工**。

- [ ] **S1.1** 新建 `world_packs/` 目录 + `WorldPack` 抽象类 (pack.yaml schema)
- [ ] **S1.2** 把现有 SCP 硬编码代码迁移到 `world_packs/scp/` (entity_roster, ticks_top20, 事件表)
- [ ] **S1.3** 统一 Agent schema (参考 [stat-machine-design.md](stat-machine-design.md) Agent dataclass)
- [ ] **S1.4** CLI 支持 `--packs scp` / `--packs scp,cthulhu,liaozhai` 启动参数
- [ ] **S1.5** PostgreSQL + pgvector 部署 (Docker Compose), 替换现有 Chroma
- [ ] **S1.6** Redis 热数据层 (当前 tick, awake agents 缓存)
- [ ] **S1.7** Event log 表 (append-only, 供 Tier 2 润色和 Tier 3 reflection 消费)
- [ ] **S1.8** `VectorAgentMemory` 重写, 后端由 Chroma 改 pgvector, 保持接口兼容
- [ ] **S1.9** 配置层 (pydantic-settings) 支持三 tier 开关和预算上限

**出口**: `python -m world_sim --packs scp` 能跑起来, 空世界, 无 LLM, 无事件。

---

## S2 · 内容生产 (编剧/研究员 × 1-2)

**和 S1 完全解耦的数据工作**。产出的 YAML 文件直接塞进 S1 搭好的 pack 目录即可。

### S2a · SCP World Pack
- [ ] **S2a.1** 从 SCP Foundation Wiki 挑 50 条最有故事张力的条目
- [ ] **S2a.2** 每条写 `personas/<id>.yaml`: persona card (< 500 字) + 属性 + 初始关系
- [ ] **S2a.3** 撰写 `events/daily.yaml` (50 条日常事件: 报告/实验/测试/巡逻/...)
- [ ] **S2a.4** 撰写 `events/spotlight.yaml` (20 条大事件: 收容失效/异常现象/内部冲突)
- [ ] **S2a.5** 撰写 `tiles/tile_types.yaml` (收容站/研究区/D-class 区/异常场)
- [ ] **S2a.6** `storyteller.yaml` (冷硬理性的 storyteller 人格)

### S2b · 克苏鲁 World Pack
- [ ] **S2b.1** 选 30 神祇 + 20 凡人角色 (调查员/教徒/仆役)
- [ ] **S2b.2** 按同样 schema 写 personas
- [ ] **S2b.3** `events/daily.yaml` (50 条: 研读古籍/街头散步/梦魇/信件往来)
- [ ] **S2b.4** `events/spotlight.yaml` (20 条: 低语降临/教团仪式/疯狂发作/神祇苏醒)
- [ ] **S2b.5** Tile 类型 (古宅/港口/阿卡姆街区/未知山脉)
- [ ] **S2b.6** Storyteller 人格 (阴郁哥特式)

### S2c · 聊斋 World Pack
- [ ] **S2c.1** 选 50 个聊斋故事主角 (聂小倩/婴宁/辛十四娘/席方平/...)
- [ ] **S2c.2** 按同样 schema 写 personas
- [ ] **S2c.3** `events/daily.yaml` (50 条: 赶考/偶遇/市井/修行/夜谈)
- [ ] **S2c.4** `events/spotlight.yaml` (20 条: 渡劫/人妖情/科考揭榜/冤案昭雪)
- [ ] **S2c.5** Tile 类型 (市井街市/书斋/荒野山寺/阴府)
- [ ] **S2c.6** Storyteller 人格 (温情烟火气)

### S2d · 跨 pack (可选, 只对混合启动生效)
- [ ] **S2d.1** `cross_pack_events.yaml` (20-30 条: SCP 特工调查聊斋狐妖, 克苏鲁污染 SCP 收容站, 等)

**出口**: 每个 pack 目录自包含, 单独 `--packs scp` 能跑出完全不同调性的世界。

---

## S3 · LLM 选型与接入 (算法/基建工程师 × 1)

**为 Tier 2/3 落地做技术准备, 与 S1/S2 解耦**。

### S3a · Tier 3 在线大模型
- [ ] **S3a.1** 注册 **DeepSeek V3** 企业账号, 跑基础 benchmark (persona 扮演 + debate)
- [ ] **S3a.2** 注册 **Qwen-Max** (阿里百炼), 同基准对比
- [ ] **S3a.3** 统一 `Tier3Client` 抽象 (adapter pattern, 方便主/备切换)
- [ ] **S3a.4** **Prompt cache** 配置 (persona_card 前缀能不能真省钱, 测一下)
- [ ] **S3a.5** Daily budget guard (超限自动降级到 Tier 2)

### S3b · Tier 2 本地小模型 (v2 选型 — 纯英文 + i18n 层)
**选型原则 (v2)**: 模型只跑英文, 中文输出由独立翻译层处理。全部国际开源。
- [ ] **S3b.1** **Phi-4 14B** 本地部署 (vLLM + 2×A100 or 4×A10), Tier 2 主力
- [ ] **S3b.2** 统一 `Tier2Client` 抽象 (OpenAI 兼容 endpoint)
- [ ] **S3b.3** 吞吐 benchmark (目标 Phi-4 ≥ 100 QPS per 2×A100)
- [ ] **S3b.4** 超时/格式错 fallback 到 Tier 1 template
- [ ] **S3b.5** 备选评估 **Gemma 4 26B A4B** (MoE, 3.8B active, Apache 2.0) 对比 Phi-4

### S3c · Tier 3 强力模型
- [ ] **S3c.1** **Gemma 4 31B** 自托管 (vLLM + 2×A100 80G), Apache 2.0
- [ ] **S3c.2** 统一 `Tier3Client` 抽象 (orchestrator / debate 用)
- [ ] **S3c.3** DeepSeek V3 云 API 作为 fallback, 自托管宕机时降级
- [ ] **S3c.4** **Prompt cache** 验证 (persona_card 前缀)
- [ ] **S3c.5** Daily budget guard + 自动降级到 Tier 2

### S3d · i18n 翻译层 (新增)
- [ ] **S3d.1** **NLLB-200** (Meta, Apache 2.0) 本地部署, 专职 en↔zh 翻译
- [ ] **S3d.2** `TranslationClient` 抽象 (batch mode, 支持缓存)
- [ ] **S3d.3** Legend rendering 输出时按 locale 自动调用翻译
- [ ] **S3d.4** 翻译结果写入 `enhanced_rendering_zh` 等 locale 字段, 持久化

### S3e · Embedding
- [ ] **S3e.1** **BGE-M3** 本地部署 (英文 + 少量中文上下文, 适用)
- [ ] **S3e.2** 和 S1.5 的 pgvector 对接

### S3f · Interview Synthesis Pipeline (英文版)
- [ ] **S3f.1** 英文扮演者 + 英文受访者双 LLM 流程
- [ ] **S3f.2** 每个 persona 产出 ~2h 英文 transcript
- [ ] **S3f.3** Transcript 灌入 pgvector 作为 agent 初始记忆 (英文)
- [ ] **S3f.4** 面向用户的 reveal-time 再翻译 (或在角色卡层面 bilingual)

### S3c · Embedding
- [ ] **S3c.1** **BGE-M3** 本地部署 (sentence-transformers or FlagEmbedding)
- [ ] **S3c.2** 或选择百炼 embedding API (量不大时用 API 比自托管合算)
- [ ] **S3c.3** 和 S1.5 的 pgvector 对接

### S3d · Interview Synthesis Pipeline
- [ ] **S3d.1** 双模型扮演脚本: 一个扮采访者, 一个基于原作素材扮演角色
- [ ] **S3d.2** 产出格式化 transcript (2h 量级, 分段带 metadata)
- [ ] **S3d.3** 一键对 S2 产出的所有 150 个 persona 批处理 (预算估算 ~ ¥500-1000)
- [ ] **S3d.4** Transcript 自动灌入 pgvector 作为 agent 初始记忆

**出口**: `Tier2Client.complete()` 和 `Tier3Client.complete()` 跑通, 能对任意 persona 调用, prompt cache 开启。

---

## S4 · Stat Machine 原型 (游戏设计师 × 1 + 后端 × 1)

**Tier 1 的三件融合实现, 是 Stage A 的灵魂**。依赖 S1 的 Agent schema 和 S2 的事件表, 但可以 S1/S2 各出一版 skeleton 后就开工, 不必等全部完成。

### S4a · AI Storyteller
- [ ] **S4a.1** `TileStoryteller` 类 (tension curve + cooldown + pack 事件池)
- [ ] **S4a.2** 三种 personality (balanced / peaceful / chaotic)
- [ ] **S4a.3** `tick_daily()` 输出候选事件列表
- [ ] **S4a.4** 单元测试: 运行 100 tick, tension curve 和 cooldown 曲线符合预期

### S4b · Agent Stat Machine
- [ ] **S4b.1** `Agent.tick_weekly()` 属性缓变 + 响应 storyteller 候选 + 自发动作
- [ ] **S4b.2** 事件表 engine (掷骰 + 条件匹配 + 结果应用)
- [ ] **S4b.3** 关系系统 (好感度、关系类型、衰减)
- [ ] **S4b.4** Life stage 推进 (年龄/寿命/死亡)
- [ ] **S4b.5** 单元测试: 一个孤立 agent 能正常成长到老死

### S4c · Historical Figure Registry
- [ ] **S4c.1** 晋升逻辑 (被触及/经历重大事件/成为势力领袖)
- [ ] **S4c.2** 降级逻辑 (长期不活跃)
- [ ] **S4c.3** 粗粒度普通 NPC 批处理

### S4d · Legend Log 层
- [ ] **S4d.1** 每类事件的 template 字符串 (各世界观独立风格)
- [ ] **S4d.2** LegendEvent 结构化数据 → 自然语言渲染
- [ ] **S4d.3** Importance scoring 函数 (见 stat-machine-design.md)

### S4e · 升级到 Tier 2/3
- [ ] **S4e.1** 重要度 ≥ 0.2 触发 Tier 2 润色 (S3b 接入)
- [ ] **S4e.2** 重要度 ≥ 0.6 触发 Tier 3 (S3a 接入) + Debate Phase
- [ ] **S4e.3** 统一 `enhance_event(event)` 入口, 三层自动路由

**出口**: 加载一个 pack, 空世界跑 100 虚拟日, legend log 数量级正确, 分布合理。

---

## S5 · Observability (DevOps / 后端 × 0.5)

从 day 1 就要有, 否则后面成本和 bug 都看不见。

- [ ] **S5.1** Prometheus metrics: per-tier call count / latency p50/p95/p99 / token spend
- [ ] **S5.2** Grafana dashboard (4-5 张图: tier 占比、日花费、延迟、错误率、fallback rate)
- [ ] **S5.3** 结构化日志 (JSON, 按 agent_id / tick / pack 可筛选)
- [ ] **S5.4** 日预算告警 (Tier 3 超 ¥150 push 通知)
- [ ] **S5.5** Alembic migrations (schema 版本化)

**出口**: 打开 Grafana 能一眼看到"今天跑了多少个 tick、Tier 3 花了多少钱、最慢的 call 是哪个"。

---

## S6 · Internal Dashboard (前端 × 1, 晚 2 周启动)

等 S1/S4 跑出数据后再开, 否则没东西展示。

- [ ] **S6.1** Next.js 项目脚手架
- [ ] **S6.2** Tile 网格视图 (简单 2D grid 即可, 不做地图)
- [ ] **S6.3** Agent 列表 + 搜索 + 详情页 (显示 persona card / 属性 / 关系 / 最近 events)
- [ ] **S6.4** 关系图视图 (Sigma.js 或 Cytoscape)
- [ ] **S6.5** Legend timeline (时间轴 + 按 importance 过滤)
- [ ] **S6.6** **"章回体 digest"**: 按虚拟日聚合当日 legend, Tier 3 润色成一段连贯叙述, 供团队每日阅读
- [ ] **S6.7** Tier/成本监控面板 (嵌入 Grafana)

**出口**: 团队任何成员打开浏览器能"读世界"。

---

## 关键依赖图 (细化版)

```
S1.1/2/3  (schema + pack 骨架)
   ↓
S1.5/6/7  (DB/Redis/event log)
   ↓
S4a/b/c   (Stat Machine 核心) ──→ S4d (legend) ──→ S4e (升级 Tier 2/3)
   ↑                                                    ↑
   │                                                    │
S2a/b/c   (pack 内容, 并行喂数据)                   S3a/b/c  (LLM 接入)
                                                        ↑
                                                    S3d (Interview 合成)

S5        全程并行, 越早越好

S6        S4 跑通数据后启动
```

---

## 团队配置建议 (最精简 MVP 团队)

| 角色 | 人数 | 主要负责 |
|---|---|---|
| 后端工程师 | 2 | S1 + S4 + S5 |
| 算法/基建 | 1 | S3 |
| 游戏设计师 | 1 | S4 设计 + 事件表方法论 |
| 编剧/内容 | 1-2 | S2 |
| 前端 | 1 (P/T 即可, 晚加入) | S6 |
| **合计** | **5-7 人** | |

---

## 第一周里程碑 (本周内可达成)

- [ ] S1: 跑起来一个空的 `world_packs/scp/` skeleton, CLI 能启动
- [ ] S2: 三个 pack 各完成 10 个 persona card (共 30 个) 作为 prototype
- [ ] S3: DeepSeek V3 和 Qwen2.5-7B 都能调通, 产出 hello-world 级 benchmark
- [ ] S4: `TileStoryteller` 和 `Agent.tick_weekly` 各出第一个能运行的版本 (可以只响应 10 种事件)
- [ ] S5: 基础 Prometheus metrics 收集到

**第一周结束能 demo 的东西**: 一个空壳世界, 加载 30 个 prototype persona, 跑 1 虚拟月, 产出若干 legend 事件 (纯 Tier 1), 能看出事件表和 persona 的组合开始"活了"。

---

## 第一周之后

每周 sprint 往前推, 每 2 周评估一次"世界有没有更好看", 直到满足 Stage A 出口标准的四条。

**最重要的纪律**: **不要开始 Stage B 的任何工作**, 不要做玩家客户端原型, 不要做 LBS 调研, 不要做 AR 技术选型。所有这些等 Stage A 达标再说。

一个 living world 类产品的生死分水岭在 "模拟器本身已经好玩"。这个门槛没跨过去, 后面所有工作都是空中楼阁。
