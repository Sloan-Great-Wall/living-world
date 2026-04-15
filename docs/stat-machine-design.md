# Three-Tier Stat Machine Design

> 世界自转的三层决策架构: 固定规则 + 本地小模型 + 在线强力模型, 按事件重要度逐级调用。
> Last updated: 2026-04-15

---

## 核心原则

**绝大多数 tick 不该花钱**。世界里大部分 NPC 在大部分时间里做的都是些可预测的小事 (吃饭/睡觉/走路/念经/扫地), 这些用固定规则 0 成本跑完即可。只有当事件**真的值得玩家看**或**真的影响世界走向**时, 才往上升级到更贵的层。

```
         调用成本 ↑           重要度 →
               │
┌──────────────┴──────────────────────────────────┐
│                                                  │
│  Tier 3: 在线强力模型 (DeepSeek V3 / Qwen-Max)     │
│  ~ $0.05-0.20 / call, 5-15s latency              │
│  用于: 玩家深度交互 / Debate Phase / 世界级事件    │
│                                                  │
├──────────────────────────────────────────────────┤
│                                                  │
│  Tier 2: 本地小模型 (Qwen2.5-7B / DeepSeek-Lite)  │
│  ~ $0.0003 / call (自托管), 200-500ms latency    │
│  用于: 日常对话 / 小事件润色 / legend 翻译         │
│                                                  │
├──────────────────────────────────────────────────┤
│                                                  │
│  Tier 1: 固定规则 (纯 Python)                     │
│  ~ 0.001 ms / call, 零 token 成本                │
│  用于: 90%+ dormant agent 的日常 tick             │
│                                                  │
└──────────────────────────────────────────────────┘
```

**预算目标**: 即便 10 万 DAU 规模, **Tier 1 占总 tick 量 ≥ 95%, Tier 2 占 4%, Tier 3 占 < 1%**。这是控制成本的生死线。

---

## Tier 1: 固定规则层

**Tier 1 不是一个模块, 是三个模块的融合**。

### 组件 A: AI Storyteller (借鉴 RimWorld)

**定位**: tile 级的"剧情节奏控制器"。它不直接扮演任何 NPC, 而是决定**这个 tile 今天该不该出事、出什么量级的事**。

```python
class TileStoryteller:
    tile_id: str
    personality: Literal["balanced", "peaceful", "chaotic"]
    tension_curve: list[float]  # 最近 N 天的"戏剧张力"
    cooldown_map: dict[EventType, int]  # 上次某类事件几天前
    
    def tick_daily(self) -> list[EventProposal]:
        # 1. 根据人格曲线和 tension_curve 决定今天的"事件密度"
        # 2. 从事件池里按权重随机抽事件候选
        # 3. 检查 cooldown (避免连续死人/连续婚配这种不合理)
        # 4. 返回 0-N 个候选事件交给组件 B 挑 NPC
```

**关键设计**:
- 三种人格: `balanced` (主力) / `peaceful` (新手区/风景区) / `chaotic` (危险 tile)
- **tension 滑动窗口**: 如果最近 7 天已经出了 3 个大事件, 自动降档
- **cooldown**: 同类大事件至少间隔 N 天 (防止"一个 tile 一周死 5 次人")
- **不同世界观的 tile 事件池不同**: SCP 收容站多"收容失效", 聊斋街市多"相遇入梦", 克苏鲁山脉多"低语降临"

### 组件 B: Agent Stat Machine (借鉴 太吾绘卷 / 鬼谷八荒)

**定位**: 单个 NPC 的属性演化与事件响应机器。

```python
@dataclass
class Agent:
    # 身份
    agent_id: str
    worldview: Literal["scp", "cthulhu", "liaozhai"]
    persona_card: str  # 固定的身份描述
    
    # 属性 (每个数值 0-100)
    attributes: dict[str, int]  # 武/智/魅/体/意志/财富/信仰/恐惧/...
    
    # 立场与标签
    alignment: str  # 正派/中立/邪派 + 世界观特有派别
    tags: set[str]  # ["学者", "妖", "教团成员", "D-class"...]
    
    # 动态状态
    inventory: list[Item]  # 道具 + 词条
    relationships: dict[str, Relationship]  # agent_id → (好感度, 关系类型)
    life_stage: Literal["童年", "青年", "壮年", "老年", "故去"]
    current_goal: str | None  # 本季度/本年度主要目标
    
    # 历史
    legend_log: list[LegendEvent]  # append-only 事件履历
    
    def tick_weekly(self, storyteller_proposals: list[EventProposal]) -> list[LegendEvent]:
        # 1. 属性缓变 (年龄增长、技艺熟练度微增)
        # 2. 响应 storyteller 的候选事件:
        #    for each proposal:
        #      if 本 NPC 符合参与条件 (tag/alignment/attribute 阈值):
        #        掷骰 (基于 attribute 和 relationship):
        #          - 成功 → 事件发生, 更新属性/关系/道具
        #          - 失败 → 记录失败 legend
        # 3. 自发动作 (基于 current_goal):
        #    查"自发事件表"(无 storyteller 介入也可能做的事)
        #    例: 拜访关系好的邻居 / 练功 / 研读SCP文献
        # 4. 返回本 tick 产生的 legend events
```

**关键设计**:
- **事件表硬编码** (MVP 阶段 300-500 条): 每条事件有触发条件 + 掷骰表 + 结果模板
- **属性缓变 (±1-3/tick)**: 确保长期稳定, 不会一周之内从菜鸟变大师
- **关系衰减**: 好感度每周轻微回归到 0 (久不联系就淡了), 大事件给大冲击
- **死亡是明确规则**: 寿命到/特定事件触发, 不是"小概率 tick 意外死"

### 组件 C: Historical Figures 层 (借鉴 Dwarf Fortress)

**定位**: 把有限算力集中在"重要 NPC"身上, 让普通 NPC 走粗粒度模拟。

```python
class HistoricalFigureRegistry:
    """
    world 里的 agent 分两档:
      - Historical Figures (大约 5-10% 的 agent):
          完整 stat machine tick, 所有细节被模拟
          个人经历可以追溯、被其他 agent 引用
      - Ordinary NPCs (90%+):
          只有最低限度状态 (存活/所在 tile/关系标签)
          不单独 tick, 只在被 storyteller 点名时参与事件
    """
    
    def promote_to_historical(self, agent_id: str, reason: str):
        """
        普通 NPC 因为某事件晋升为 historical figure:
        - 被玩家接触过
        - 经历了重大事件 (破境/继承宝物/引发冲突)
        - 成为某个势力领袖
        """
    
    def demote_if_inactive(self, agent_id: str):
        """
        长期不活跃的 historical figure 降级回普通, 省算力
        但 legend_log 保留 (他的事迹仍可被提及)
        """
```

**关键设计**:
- 初始化时: 每个世界观选 10-20 个"世界级重要角色"作为永久 historical figures (SCP-173, 克苏鲁本尊, 聂小倩这种)
- 玩家接触过的 NPC 自动晋升 (保证玩家关心的 NPC 是细粒度模拟的)
- 普通 NPC 不是摆设, 他们提供世界的"生态背景", 但只在被 storyteller 点名时加入事件

### 三组件协作流程

```
每个 tile 每周一次 tick:

 [Storyteller] 提出本周候选事件 (0-3 个)
       │
       ▼
 [HistoricalFigureRegistry] 筛出本 tile 的 historical figures
       │
       ▼
 [Agent.tick_weekly] 每个 historical figure 响应候选事件
       │
       ▼
 [Agent.tick_weekly] 每个 historical figure 自发动作
       │
       ▼
 [OrdinaryNPC 批处理] 被点名的普通 NPC 做简化响应
       │
       ▼
 收集本 tile 本周所有 LegendEvent
       │
       ▼
 检查是否触发 Tier 2/3 升级 (下一节)
       │
       ▼
 写入 legend_log + 更新 world state
```

---

## 升级判定: 什么时候跳到 Tier 2 / Tier 3

每个 Tier 1 产出的 LegendEvent 都要做一次**重要度评分**:

```python
def score_event_importance(event: LegendEvent) -> float:
    score = 0.0
    
    # 参与者重要性
    if any(p.is_historical_figure for p in event.participants):
        score += 0.3
    if any(p.is_touched_by_player for p in event.participants):
        score += 0.4
    
    # 事件类型
    if event.kind in ("死亡", "继承", "联姻", "决斗", "破境", "收容失效", "降临"):
        score += 0.5
    elif event.kind in ("日常对话", "旅行", "练功"):
        score += 0.05
    
    # 关系网影响
    score += min(0.2, 0.05 * len(event.affected_relationships))
    
    # 玩家在线且在附近
    if event.tile_has_active_player:
        score += 0.3
    
    return score

# 分档
if score < 0.2:
    # Tier 1 的 template 生成 legend 字符串即可, 不调模型
    pass
elif score < 0.6:
    # Tier 2: 本地小模型润色, 让 legend 读起来更生动
    enhance_with_local_model(event)
else:
    # Tier 3: 在线强力模型, 可能触发 Debate Phase
    promote_to_spotlight(event)
```

---

## Tier 2: 本地小模型层

**定位**: 低成本的"文本润色 + 简单推理"引擎。

### 适用场景

- **Legend log 润色**: Tier 1 的 template 输出 "贾宝玉 与 林黛玉 在 潇湘馆 发生争执, 好感度 -15", Tier 2 改写成 "午后潇湘馆中, 宝玉又因一句无心话惹得黛玉落泪, 这已是这月第三次了"
- **普通玩家对话**: 玩家随便跟一个路人 NPC 说几句话, Tier 2 即可, 不值得调 Opus
- **小事件叙事生成**: 两个小 NPC 相遇的细节描述
- **属性变化的自然化解释**: "为什么武力 +3" → "因为这周坚持晨练"

### 模型选择 (2026-04 最新, 决策于 v2)

**选型原则 (v2)**:
1. 国际开源优先, 避开中国模型生态锁定
2. **模型只需英文能力**——所有内容以英文为 source of truth, 面向中文用户的输出通过独立 i18n 翻译层处理
3. 许可证干净优先 (MIT / Apache 2.0 > Llama License > Gemma Terms > 商业协议)

| 模型 | 参数 | 英文能力 | 授权 | 用途 |
|---|---|---|---|---|
| **Phi-4** (Microsoft) | 14B | MMLU ~88%, 小模型推理 SOTA | **MIT** | **Tier 2 主力** — legend 润色 + 路人对话 |
| **Gemma 4 26B A4B** (Google, MoE) | 26B 总 / **3.8B active** | Arena rank 6 | **Apache 2.0** | Tier 2.5 (可选) — 成本接近 4B 密集 |
| **Gemma 4 31B** (Google) | 31B | MMLU Pro 85.2% / AIME 89.2% | **Apache 2.0** | **Tier 3 自托管首选** |
| **Llama 4 Scout** (Meta) | 17B active MoE | 推理偏弱于 Gemma 4 | Llama 4 License | 备份 (许可证不如 Apache) |
| DeepSeek V3 (云 API) | — | 英文强, 在中国境内可用 | 商业 | **Tier 3 云端 fallback** — 如 GPU 不足 |

**MVP 推荐配置 (v4 — 分 Dev / Prod 两档)**:

### Dev Tier (MacBook 本地开发 & 调试, 零 GPU 依赖)
- **主力**: **Gemma 3 4B** via Ollama
  - 4-bit 量化 ~3GB, M1/M2/M3 MacBook 16GB 舒服跑
  - `ollama pull gemma3:4b`, 对接我们 `OllamaClient`
  - 身兼 Tier 2 + Tier 3 (质感有限, 但够验证整条 pipeline)
- **备选**: Phi-3.5 Mini 3.8B (MIT) / Llama 3.2 3B (Meta)

### Prod Tier (Stage A 末期上 GPU 服务器后)
- **Tier 2**: Phi-4 14B (AWQ 4-bit) on 单 RTX 4090 or A10, ~9GB VRAM, MIT
- **Tier 3**: Gemma 4 31B on 2×A100 80G, Apache 2.0
- **Tier 3 云 fallback**: DeepSeek V3 API

### 为什么这样分
- MVP 前期要的是**整条 pipeline 能跑通**, 不是叙事质感。Gemma 3 4B 在 MacBook 跑够了
- 架构用 OpenAI 兼容 endpoint 抽象, 从 Ollama 切 vLLM/Phi-4 是改一行配置
- 没人需要一开始就买 GPU 机器

### i18n / Translation Layer (新增)

因为模型只跑英文, 面向中文用户需要独立翻译层:

```
内容 (英文 source of truth)
   ├─ personas/*.yaml 的 persona_card 用英文撰写
   ├─ events/*.yaml 的 template 用英文撰写
   └─ 保留可选的 display_name_zh 字段做界面展示
                │
                ▼
LLM 流水线 (纯英文): Tier 1 template → Tier 2 Phi-4 → Tier 3 Gemma 4
                │
                ▼
Translation Layer (output 侧)
   ├─ 用户 locale=en → 直接返回
   ├─ 用户 locale=zh → 调翻译:
   │     ├─ 首选: NLLB-200 (Meta, Apache 2.0, 200 语言, 专门翻译模型)
   │     └─ 次选: Phi-4 同机复用 (Phi-4 翻译一般但可接受)
   └─ 翻译结果缓存 (同 event.spotlight_rendering 不重复翻)
```

**好处**:
1. 模型选型去掉"中文能力"这个强约束, 选择空间大 10 倍
2. 语言扩展容易 (日/韩/英 用户接入只需换翻译目标)
3. 测试集和 benchmark 都基于英文主流数据集, 可信度高
4. 聊斋文言等细腻中文语感在**原文 display + 英文模型 + 中文翻译**三层混合下会有损失——接受这个 tradeoff, 因为模型自由度远大于"硬用中文模型"

### 关键设计

- **输入永远带结构化 context**: 不是让小模型自由发挥, 而是"这是一段 template, 帮我润色成 X 风格"
- **输出必须可被结构化解析**: 用 JSON output 或明确分段, 避免幻觉破坏 stat machine
- **有 fallback**: 超时/格式错 → 退回 Tier 1 template

---

## Tier 3: 在线强力模型层

**定位**: 真正"贵且慢但效果拉满"的层。

### 适用场景

- **玩家深度对话** (awake interaction with meaningful choice)
- **Debate Phase** (详见 [flow-loops.md](flow-loops.md) Flow 4)
- **世界级 spotlight event** (SCP 收容失效 / 克苏鲁现身 / 聊斋大妖转世)
- **Reflection 层压缩** (把 100 条 events 压成 narrative summary)
- **玩家回来时的"追述"** (你离开时发生了什么)

### 模型选择 (中国版)

| 模型 | 定位 | 单价参考 (2026) | 适用 |
|---|---|---|---|
| **DeepSeek V3** | 综合性价比最强 | ~¥2-4 / 1M output tokens | 主力, 大部分 Tier 3 调用 |
| **Qwen-Max** (通义千问) | 阿里百炼, 稳定性强 | ~¥20 / 1M output tokens | Debate orchestrator |
| **Kimi (Moonshot)** | 超长 context | ~¥10-30 / 1M | 反思层 / 长对话 |
| **Doubao 1.5 Pro** | 字节, 对话自然 | ~¥10 / 1M | 玩家对话 |
| **GLM-4-Plus** | 智谱, 支持 function call | ~¥50 / 1M | 备份 |

**MVP 建议**: DeepSeek V3 主力 + Qwen-Max 作为 debate orchestrator 的备份。双供应商可以应对单家宕机/限流。

### 关键设计

- **5 段式 prompt composition** (见 [tech-glossary.md](tech-glossary.md) 第 7 节) 严格执行
- **Hard budget per day**: 每天 token 预算上限, 超了自动降级回 Tier 2
- **Cache 能 cache 的都 cache**: persona_card 这种不变的前缀, 开启 prompt cache
- **并发调用时用 asyncio.gather**: Debate Phase 里 5 个 worker 并发跑, 不要串行

---

## 升级与降级的边界案例

| 情景 | 正确 Tier | 错误 Tier |
|---|---|---|
| 玩家走路经过 NPC, 随便说一句"你好" | Tier 2 | ❌ Tier 3 (浪费) |
| 玩家决定是否帮 NPC 抢夺某件 SCP | Tier 3 | ❌ Tier 1 (错失关键剧情点) |
| 两个普通村民结婚 | Tier 1 template | ❌ Tier 2 (日常事件不值润色) |
| 两个 historical figure 结盟 | Tier 3 (触发 debate: 对此结盟其他 agent 怎么看) | ❌ Tier 1 (错失叙事机会) |
| 一个无名小妖死了 | Tier 1, 记入 log 即可 | ❌ Tier 2 (不值) |
| 玩家接触过的 NPC 死了 | Tier 3 (玩家需要看到完整讣告叙事) | ❌ Tier 1 (冷冰冰一行 log) |
| 每日 reflection 层压缩 | Tier 3 (Kimi/DeepSeek 长 context 版) | ❌ Tier 2 (小模型压不好长序列) |

---

## 监控与降级

必须内置的运行时监控:

- **Per-tier call rate** (每分钟每层调用次数)
- **Tier 3 daily spend** (今日 token 花费)
- **Latency p50/p95/p99** (每层延迟)
- **Fallback rate** (Tier 3→2, Tier 2→1 的降级发生率)

**自动降级策略**:
- Tier 3 每日预算用完 → 全部 Tier 3 请求降到 Tier 2
- Tier 2 服务异常 → 全部 Tier 2 请求降到 Tier 1 (纯 template)
- 即便完全没有 LLM, 世界仍然可以自转 (Tier 1 100% 覆盖)

这是这个架构最重要的保险——**世界的"活着"不依赖 LLM 能不能用**, LLM 只是"让它更生动"的加层。
