# Product Direction Decision Record

> Status: **Direction A selected** — consumer-facing, gamified, LBS-anchored living-world AI agent network.
> Last updated: 2026-04-15

---

## 1. 思考过程回顾

### 起点：三基因缝合设想

最初的产品灵感是把三个东西缝起来：

- **MiroFish AI** — multi-stakeholder agent simulation 做 decision prediction
- **Pokémon Go** — LBS + AR 地理锚定玩法
- **Claude Agent SDK** — 底层 agent orchestration runtime

### 为什么不能无缝融合

三个基因在产品维度上是本质冲突的：

| 维度 | Pokémon Go | MiroFish | Claude Agent |
|---|---|---|---|
| 用户 | C 端大众 | B 端决策者 | 基础设施 |
| 频次 | 日活 | 偶发 | N/A |
| 付费 | F2P + IAP | 订阅 $70/月 | API 按量 |
| 价值主张 | 娱乐 | 决策质量 | 引擎能力 |

硬缝会得到 "B 端用户嫌不够严肃、C 端用户嫌不够好玩" 的四不像。

### 三个候选方向

在想象空间里拆出了三个独立产品方向：

- **方案 A: Spatial Living World** — consumer AR 娱乐
- **方案 B: Decision Theatre** — B2B 决策剧场（MiroFish 正面升级版）
- **方案 C: Agent-as-Infrastructure** — B2B2C 平台

### 决策：选 A

团队基因和兴趣更偏 C 端游戏化方向，所以锁定方案 A。B 和 C 暂存为后续可能的 pivot 路径或 infra 副产品。

---

## 2. 方案 A 的产品定义

### One-liner

> **一个真实世界里的活 NPC 网络——每个地点住着会记住你、有自己人生轨迹、互相有关系、离线也在继续生活的 AI agent。**

### 核心体验假设

灵感直接来自三款"活世界"类型游戏：

- **太吾绘卷** — NPC 有完整 lifetime (出生/成长/成家/死亡)、功法传承、恩怨继承
- **鬼谷八荒** — NPC 有属性 / 功法 / 道具 / 立场，玩家不在时自行修炼历练
- **博德之门 3 (BG3)** — NPC 有深度背景故事和与其他 NPC 的动态关系网

这三款游戏证明：**"玩家离线时世界仍在自转" 是玩家最上瘾的体验之一**，但以往靠 hand-crafted state machine + event table 硬编码，内容天花板低。

**我们的杠杆：用 generative agent 替代 hand-crafted simulation，让世界在自然语言层面 emergent**，内容天花板高一到两个数量级，且每个玩家看到的世界是真正不同的。

### 核心玩法 Loop

1. **Discover** — 玩家在真实街区移动，发现附近 tile 里住着的 agent（可能是刚搬来的新人、有故事的老居民、落魄的流浪者）
2. **Meet & Bond** — 对话建立关系。agent 会记住玩家，形成 per-player memory scope
3. **Entangle** — agent 有自己的目标（开店、寻亲、复仇），玩家可选择卷入或旁观
4. **Absent Evolution** — 玩家离线时，agent 之间仍按各自 persona 互动，世界状态持续演进
5. **Return & React** — 玩家回来时，世界已经变了。agent 会提起"你上次走后发生的事"

### 与 Pokémon Go 的关键差异

| 维度 | Pokémon Go | 我们 |
|---|---|---|
| 收集对象 | 静态数值 pokemon | 有记忆/立场/关系的 persona agent |
| 交互 | 抛球 + 数值对战 | 自然语言对话 + 关系博弈 |
| 离线世界 | 死的 | 活的、持续 evolve |
| IP 来源 | Pokemon 授权 | 虚拟作品角色库 (cosplay-style, 下节) |

---

## 3. Persona 来源策略

### 问题背景

Stanford 2024 年的 [1000 People](https://arxiv.org/abs/2411.10109) 论文证明 **interview-based persona 碾压 bio-based persona**——persona 可信度是这类产品的核心壁垒。但我们做 C 端娱乐游戏，不可能像 Stanford 那样采访 1052 个真人。

### 选择：Character-derived persona (cosplay 路径)

团队倾向于从虚拟作品提炼角色作为 persona 库——**cosplay 式**的二次创作角度。

为什么这条路对娱乐产品更合适：

- **已有粉丝心智** — 玩家遇到"像某某角色"的 agent 会立刻上头
- **素材充足** — 小说、动漫、游戏、影视里的角色有大量对话/行为文本可以合成出 "interview transcript" 等价物
- **合规相对可控** — 不用处理真人隐私；但仍需处理 IP 合规
- **Narrative 密度高** — 虚构角色的人生故事往往比普通真人更戏剧化，更适合游戏

### 实现方法（待验证）

借鉴 1000 People 的 interview-as-memory 思路，但输入不是真人访谈而是：

1. **原作文本** — 角色相关的小说章节、剧情对话、世界观设定
2. **合成 interview** — 用一个大模型扮演采访者对角色发问，用另一个大模型基于原作扮演角色回答，生成 2 小时量级的对话 transcript
3. **灌入 memory stream** — transcript 作为该 agent 的初始长期记忆
4. **属性 + 词条结构化层** — 借鉴太吾/鬼谷的 stat machine，给每个 agent 加一层结构化属性（武力/智谋/魅力/背景标签/道具词条），作为 LLM 推理时的硬约束

### 待决策点

- **IP 策略**：原创角色 / 公共领域角色 (莎翁、金庸已过期作品等) / 授权合作 / 玩家 UGC 上传
- **Persona 数量级**：冷启动需要多少个？我的猜测是 200-500 个精品 persona + UGC 长尾
- **地理分配逻辑**：哪些 persona 出现在哪些 tile？按文化区域？随机？玩家拉新？

---

## 4. 愿景：可实现性评估

> "NPC 在玩家不在的时候也会相互交互，产生符合自己设定的新人生故事，变化自己的属性设定、道具词条，甚至反映在游戏世界本身上。"

**结论：可实现，但需要解决三个工程约束。**

### 可实现的部分

- **Smallville 已经证明** 25 个 agent 在 2 天游戏内时间里会自发形成派对邀请、竞选活动等 emergent 事件
- **属性/词条 evolution** 是经典 game design 问题，和 LLM 正交
- **关系网演进** LLM 处理关系推理比 hand-crafted 好做
- **世界状态反映** world state 写回 Redis / DB 是工程问题

### 三个必须解决的工程约束

#### 约束 1: Token 成本

离线世界自转的最大风险是成本失控。假设一个城市 10 万个 active agent，每个 agent 每小时 tick 一次，每次一个 LLM call——哪怕只用 Haiku，一天也是天文数字。

**对策：分层 tick 频率 + model routing**

- **Dormant tier** (默认)：agent 完全不跑 LLM，只按结构化 stat machine 推进（借鉴鬼谷八荒）
- **Awake tier** (玩家附近 / 剧情相关)：Haiku 跑日常对话和小事件
- **Spotlight tier** (关键剧情节点)：Sonnet / Opus 跑重大决策和高质量 narrative

#### 约束 2: 状态一致性

Agent 的记忆、属性、关系、道具分散在 vector DB / Redis / 关系 DB 里，离线 tick 并发写会冲突。

**对策**：

- Agent 的"身份"按 `agent_id` 分片，同一 agent 的更新单线程处理
- 世界级别的事件通过 event sourcing 补偿 (CQRS 风格)
- 玩家回来时的"追溯叙述"由 orchestrator 拉出时间线重新总结

#### 约束 3: 叙事连贯性

LLM 自由发挥会飘。Agent A 今天说"我恨 B"，三天后可能自己忘了。

**对策**：

- 结构化属性 (好感度 / 标签 / 事件记录) 作为**硬事实**约束
- Reflection 层周期性把 raw events 压缩成 persona 级别的叙事 summary
- 关键事件 (死亡、婚姻、主要道具) 写入不可变 log, LLM 不能覆盖

---

## 5. 开工前待锁定的决定

### 已锁定 (2026-04-15)

- [x] **目标市场**: **中国版优先** — MVP 就面向中国大陆用户设计，而非先海外再国内
- [x] **世界观 (World Pack) 策略**: **SCP Foundation / 克苏鲁神话 / 聊斋志异** 作为三个**独立的 world pack**, 可单独启动任一个世界的模拟, 也可混合启动多个 pack 共享同一 world space。三者不强行融合, 但提供 cross-pack event 机制让混合模式下产生跨世界观叙事
- [x] **开发路线**: 无玩家虚拟世界模拟器 → 有玩家虚拟世界模拟器 → 有玩家 AR 世界模拟器 → AR 宝可梦玩法层 (详见 mvp-roadmap.md)
- [x] **Phase 1-2 体验基调**: **DnD 跑团游戏感觉** — 文字+骰子+叙事驱动为主, AR/视觉是后期加层
- [x] **Stat Machine 架构**: 三层调用 — 固定规则 (storyteller + stat machine + DF historical figures) + 本地小模型 + 在线强力模型, 按重要程度逐级调用 (详见 stat-machine-design.md)

### 中国版带来的技术栈变更

| 组件 | 海外方案 | 中国版替代 |
|---|---|---|
| **LBS 精确定位** | Niantic VPS (不可用) | GPS + Wi-Fi 指纹 + IMU 融合, 米级精度 (退化 tile-based) |
| **地图底图** | Mapbox | 高德 / 百度 / 腾讯 Maps SDK |
| **Tier 3 大模型** | Claude Opus/Sonnet | **DeepSeek V3 / Qwen-Max / GLM-4 / Kimi / Doubao** (阿里百炼, 选一到两家) |
| **Tier 2 本地小模型** | Llama 3.2 | Qwen2.5-7B / DeepSeek-V2-Lite (国内开源) |
| **Embedding** | OpenAI text-embedding-3 | BGE-M3 / Qwen3-Embedding (国内 SOTA) |
| **STT/TTS** (如需) | Whisper / ElevenLabs | 讯飞 / 阿里达摩院 / 字节火山 |
| **AR 框架** | ARKit (iOS) + ARCore | ARKit (iOS 原生, 中国可用) + ARCore 国内版 (华为/小米/OPPO/vivo) |
| **坐标系** | WGS-84 | **GCJ-02 (国测局加密)** 或 BD-09 (百度) |
| **合规** | GDPR | **网络游戏版号 + ICP + 实名制 + 未保** |

### 尚待锁定

- [ ] **首城选择** — 北上广深一线还是杭州/成都二线? 影响 VPS-退化策略的地理建图工作量
- [ ] **首批大模型供应商** — DeepSeek + Qwen 二选一或双供应商备份?
- [ ] **冷启动 persona 库规模** — 建议: 三世界观各 50 个精品 = 150 (保守) 或各 100 = 300 (理想)
- [ ] **MVP 平台** — iOS-first vs Android-first? (中国 Android 占比高, 但 iOS 付费强)
- [ ] **是否走版号路线** — 版号周期 6-18 个月, 影响商业化时间表。MVP 内测阶段可先走"测试号"

---

## 6. 非目标 (Non-goals)

明确**不做**的事，避免 scope creep：

- ❌ B 端决策模拟（方案 B 的事，归档）
- ❌ 裸 API 平台（方案 C 的事，归档）
- ❌ 宠物收集数值对战（这是 Pokémon Go，不是我们）
- ❌ Agent 财务建议 / 法律建议等 high-stakes 输出
- ❌ 真人 persona（1000 People 方法论暂不走）
