# Docs — Living World Simulator

项目设计文档索引。**此目录已加入 .gitignore, 不进仓库, 只在本地和团队内共享**。

## 文档列表 (建议阅读顺序)

| # | 文档 | 内容 | 读完后能答出 |
|---|---|---|---|
| 1 | [product-direction.md](product-direction.md) | 产品定位, 方向选 A 的推导, 中国版决策 | 这是什么产品, 为什么这么定 |
| 2 | [architecture.md](architecture.md) | 7 层整体技术架构, 数据流, 选型理由 | 系统骨架长什么样 |
| 3 | [tech-glossary.md](tech-glossary.md) | 关键术语表 (tick, agent, LangGraph, ...) | 讨论时大家说的是同一个东西 |
| 4 | [stat-machine-design.md](stat-machine-design.md) | 三层 stat machine 详细设计 | 世界怎么自转, 钱怎么花 |
| 5 | [flow-loops.md](flow-loops.md) | 4 张核心 flow diagram | 运行时每个循环长啥样 |
| 6 | [mvp-roadmap.md](mvp-roadmap.md) | Stage A/B/C/D 全阶段规划 | 从 MVP 到成熟产品要几步 |
| 7 | [next-steps.md](next-steps.md) | **Stage A MVP 的 6 条并行工作线** | 明天该干什么 |
| 8 | [lbs-infrastructure.md](lbs-infrastructure.md) | Niantic + 中国版 LBS 预研 (Stage C 用) | 为什么中国版不能用 VPS |

## 当前范围锁定

- **MVP 范围**: Stage A — 无玩家、非 VR、自动运行的虚拟世界模拟器
- **世界观**: SCP + 克苏鲁 + 聊斋 三个独立 world pack, 可单独可混合
- **目标市场**: 中国版优先
- **LLM 选型**: Qwen3-8B (Tier 2 中文) + Gemma 3 12B (英文辅助) + DeepSeek V3 (Tier 3)

## 维护原则

- 讨论有实质决策后, 立即更新相关文档, 保持"文档 = 当前真相"
- 废弃决策不删除, 改为 "~~废弃~~" 或归档到新章节, 保留决策 trail
- 新主题一律先写 doc, 再写代码
