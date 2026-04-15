# LBS Infrastructure — Stage C 预研文档

> 地理位置服务基础设施分析。
> **Stage A MVP (当前) 不用 LBS**, 此文档为 Stage C 预研, 避免后续遗失分析。
> Last updated: 2026-04-15

---

## 1. 背景

Stage C (有玩家的 AR 世界模拟器) 需要把虚拟 tile 绑定到真实地理位置, 让玩家走到实地才能触发 agent interaction。
本文档记录为此做的技术选型分析。

---

## 2. Niantic Spatial 生态

### 2.1 产品线

Niantic Labs 2025 年 5 月分拆出 **Niantic Spatial** 作为独立公司, 把 Pokémon Go 多年积累的 LBS/AR 基础设施产品化:

| 产品 | 功能 | 免费额度 |
|---|---|---|
| **Niantic Spatial SDK** (原 Lightship ARDK) | Unity/iOS/Android AR SDK, 包含 occlusion / semantic segmentation / shared AR | 有免费 tier, 按 MAU 计费 |
| **VPS 2.0** (Visual Positioning System) | 基于视觉的厘米级定位, 覆盖 1M+ "hot spots" | **25,000 calls/月免费**, 超出按量 |
| **Multiplayer API** | 多人 AR 同步 | 6 个月 + 50K MAU 以下免费 |
| **Scaniverse** | 用户扫描生成 3D 模型 | 消费者版免费 |

### 2.2 VPS 的核心价值

VPS 是 Niantic 的**真·moat**:
- 训练数据来自 Pokémon Go 玩家 10 年累计上传的 **30 billion 张图片** (众包, 别家无法复现)
- 精度**厘米级**, GPS 只能做到米级, 差 1-2 个数量级
- 能让虚拟物体精确锚定到真实建筑的某个角落 (而不是"这条街附近")

### 2.3 关键时间节点

- **2026-02-27**: `Lightship.dev` 已停用, 迁移到 `nianticspatial.com` 和 `scaniverse.nianticspatial.com`
- **2026-02-28**: 8th Wall 平台关停 (前 Niantic 收购的 web AR 平台)
- **2027-02**: 8th Wall 托管内容彻底下线

---

## 3. 中国版不能用 Niantic 的三层原因

### 3.1 数据合规层
VPS 需要用户手机实时上传相机图像到服务器做匹配。中国《数据安全法》《个人信息保护法》《地图管理条例》要求:
- 地理空间数据必须**境内存储**
- 精度高于 **1:50000** 的数据需要测绘资质
- 摄影画面涉及人脸/车牌等需要额外 PII 合规

Niantic 服务器在境外 → 数据出境违法。

### 3.2 部署覆盖层
Pokémon Go 从未在中国大陆正式上线:
- 2017 年与**网易**有过合作协议, 但至今没落地
- VPS hot spots 集中在海外 Pokémon Go 玩家密集地区
- **中国大陆 VPS 覆盖基本为零**

### 3.3 地图基础层
中国地图必须用国测局加密坐标系:
- 国产地图: **GCJ-02** (国测局火星坐标) 或 **BD-09** (百度再加密)
- 海外数据用的是 **WGS-84** (GPS 原始坐标)
- WGS-84 直接展示在中国地图上会偏移 50-500 米 (违法)

---

## 4. 中国版技术栈替代方案

### 4.1 地图底图 SDK

| 供应商 | 优势 | 劣势 |
|---|---|---|
| **高德地图** (阿里系) | 国内 POI 覆盖最全, SDK 成熟, 开发文档友好 | 收费偏高 |
| **腾讯地图** | 微信生态集成好 | POI 次于高德 |
| **百度地图** | 国内第一个做 LBS, 老牌 | SDK 体验一般 |

**推荐**: **高德 Unity SDK + iOS/Android native SDK**, 国内事实标准。

### 4.2 精确定位 (VPS 的替代)

**残酷事实: 国内目前没有 VPS 等价产品**。可行的退化方案:

| 方案 | 精度 | 成本 |
|---|---|---|
| 纯 GPS | 5-30 米 | 免费 |
| GPS + Wi-Fi 指纹 (蒲公英/天地图) | 3-10 米室外, 5-20 米室内 | 中 |
| GPS + IMU 融合 (手机加速度计+陀螺仪) | 3-8 米 + 短时高精度 | 低 |
| GPS + Wi-Fi + BLE + IMU 多源融合 | 1-5 米最优场景下 | 高 |
| 商汤/旷视 SLAM 方案 | 0.5-2 米 (但要预建图) | 高 + 需合作 |

**推荐**: MVP 阶段用 **GPS + Wi-Fi 指纹 + IMU**, 精度 5-15 米。我们的 tile 是 ~100m H3 cell, 精度够用。不做厘米级 AR 锚点, 放弃"pokemon 站在这桌上"的特效, 接受"pokemon 就在街区里"的定位粗细度。

### 4.3 AR 渲染

| 平台 | 选择 | 备注 |
|---|---|---|
| iOS | **ARKit** | 国内可用, 成熟稳定, App Store 认可 |
| Android | **ARCore for China** | Google 和华为/小米/OPPO/vivo 合作版, 国行机型原生支持 |
| 跨平台 | Unity / Unreal | 建议 iOS/Android 都原生, 不用 Unity |

---

## 5. Stage C 切入策略

### 5.1 首城选择建议

- **杭州** 或 **成都**: 二线头部, 玩家活跃度高, 政策环境相对友好, 本地合作资源好找
- **不建议首选北上广深**: 监管密集, 试错成本高

### 5.2 分阶段铺设

```
Stage C Alpha: 首城 1 个 区 (~3 km²)
  ├─ 人工规划 100-200 个 tile
  ├─ agent 分配到有意义的地标 (商圈/公园/书店)
  └─ 10-50 玩家 closed beta

Stage C Beta: 首城扩展 (~30 km²)
  ├─ 规划 500-1000 tile
  └─ 1000 玩家

Stage C GA: 首城全域 + 2 座次城
  └─ H3 cell 自动生成, UGC 补足
```

### 5.3 反作弊

Pokémon Go 吃过大亏, 必须从 day 1 开始:
- GPS mock 检测 (多数 Android 模拟器可识别)
- 速度校验 (人类步行 < 10 km/h, 车速 > 20 km/h 拒绝或降级体验)
- 设备指纹 (防账号工作室)
- Honeypot tile (故意放无法物理到达的 agent 抓作弊)

---

## 6. Stage A MVP 阶段的处理

**完全不碰 LBS**。
- world tile 用虚拟坐标 (`tile_id: "wujin-lane-003"`), 不绑真实地理
- Dashboard 用抽象 2D grid 展示, 不用地图 SDK
- 玩家不存在, 也不需要 GPS

以上技术栈选型留存文档, Stage C 启动时直接按本文档执行采购和选型。

---

## 7. 长期风险记录

- **Niantic 单一供应商锁定风险**: 如果未来出海, 深度集成 VPS 后迁移成本高
- **国内 VPS 空白期风险**: 如果商汤/旷视/高德 2026-2028 推出等价产品, 要评估替换
- **合规政策漂移风险**: 地图资质、游戏版号、未保政策变化会影响 LBS 玩法
- **电池/流量投诉**: LBS + AR 是手机重度耗能场景, 必须做省电模式

Sources:
- [Niantic Pricing](https://www.nianticspatial.com/pricing)
- [Niantic Large Geospatial Model](https://nianticlabs.com/news/largegeospatialmodel)
- [知乎: VPS 众包建图分析](https://zhuanlan.zhihu.com/p/519884545)
