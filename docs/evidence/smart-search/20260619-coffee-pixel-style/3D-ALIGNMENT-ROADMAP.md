# Crossroads Agent Café 3D 全面对齐 Claw3D — 执行 Roadmap

> 📌 **这是一份交付给实施 Agent 的任务书。** 拿到此文档的 Agent 无需任何历史对话上下文，按本文档即可独立执行。
>
> **生成时间**：2026-06-20 ｜ **来源**：基于对两个项目的逐文件代码勘察 ｜ **决策人**：项目 Owner
> **状态**：待执行（见文末「进度记录」）

---

## 0. 给执行 Agent 的必读说明

### 0.1 你的任务

把 **Claw3D-main** 项目的 3D 渲染能力（`src/features/retro-office/`）**全面移植/对齐**到 **crossroads-agent-cafe** 项目的前端（`frontend/src/office3d/`），让 coffee 的 3D 咖啡厅从"能跑的简化版"升级到 Claw3D 级别的沉浸感与可玩性。

**核心策略**：**数据驱动 + 逐组件移植**。绝不整体复制 Claw3D 的 7248 行业务外壳，只搬「纯 3D 能力」（渲染内核/模拟/相机/交互/模型/调试）。

### 0.2 动手前必读文件（按顺序）

读完这些再开工，否则会踩雷：

| 序 | 文件 | 为什么必读 |
|----|------|-----------|
| 1 | `D:\temp\EVOMAP\coffee-ai-boss\docs\3D.MD` | coffee 现有 3D 重构计划，含后端契约约束、禁区、验收标准 |
| 2 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\CLAUDE.md` | coffee 前端完整架构（路由/事件管线/已知移植残留）|
| 3 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\screens\OfficeScene.tsx` | 当前 3D 场景入口（Canvas 装配）|
| 4 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\office3d\core\constants.ts` | 坐标系常量（SCALE=0.018, CANVAS 1800×720）|
| 5 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\office3d\core\geometry.ts` | `toWorld` 投影 + 家具 footprint |
| 6 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\office3d\objects\furniture.tsx` | 四张映射表（GLB/SCALE/TINT/Y_OFFSET）+ 渲染器 |
| 7 | `D:\temp\EVOMAP\coffee-ai-boss\frontend\src\net\api.ts` **顶部注释** | ⚠️ ws 事件契约是只读的，role/action 集合不可改 |
| 8 | `D:\temp\EVOMAP\Claw3D-main\src\features\retro-office\RetroOffice3D.tsx` | 移植来源主入口（7248 行，**只取其中函数/组件**）|

### 0.3 操作铁律（违反一条就返工）

1. **路径永远用双引号包裹**（Windows 环境）—— `"D:\temp\EVOMAP\coffee-ai-boss\..."`。
2. **绝不整体复制 `RetroOffice3D.tsx`**——它深度耦合 gateway/store/onboarding。只能逐函数/逐组件按 Phase 拆解移植。
3. **ws 事件契约只读**——`/ws/visualization` 的 role 集合 `{customer,waiter,cashier,barista,manager}` 和 action 集合不可改；改后端需同步前端 `roleMap.ts`。
4. **不动后端业务**——`/chat`、`/admin/restaurant-state`、订单/支付逻辑零修改。
5. **不碰 Claw3D 业务**——gateway/Hermes/远程办公室/district 多区域/Skills Marketplace **不搬**（见第 3 节禁区）。
6. **保留 OrbitControls**——coffee 已有，是优势。FollowCam 作为聚焦增强**叠加**，不替换。
7. **每加一个 system 量一次 fps**——性能回归即停。
8. **代码注释语言跟随现有文件**——coffee 前端是英文注释，保持一致。
9. **改前先读**——修改任何现有文件前先 Read，理解上下文再 Edit。
10. **不擅自 git 提交/建分支**——除非 Owner 明确要求。

---

## 1. 项目背景

### 1.1 双项目定位

| 项目 | 绝对路径 | 角色 |
|------|---------|------|
| **crossroads-agent-cafe** | `D:\temp\EVOMAP\coffee-ai-boss` | 🎯 **目标项目**。3D 咖啡厅可视化（咖啡师/收银/服务员/主管/访客），后端 FastAPI Python |
| **Claw3D-main** | `D:\temp\EVOMAP\Claw3D-main` | 📦 **移植来源**。3D AI Agent 虚拟办公室，功能完整但业务耦合重 |

### 1.2 技术栈对照（两边一致，可直接移植）

| 依赖 | coffee | Claw3D | 备注 |
|------|--------|--------|------|
| React | 19.2 | 19.x | ✅ 一致 |
| @react-three/fiber | 9.5 | 9.x | ✅ 一致 |
| @react-three/drei | 10.7 | 10.x | ✅ 一致 |
| three | 0.183 | 0.183 | ✅ 一致 |
| Vite | 6.0 | 6.x | ✅ 一致 |
| TypeScript | 5.6 | 5.6 | ✅ 一致（strict）|

### 1.3 coffee 前端目录速览（移植落点）

```
frontend/
├── src/
│   ├── office3d/              # ⭐ 3D 渲染内核（移植主战场）
│   │   ├── core/              # constants/geometry/navigation/types/furnitureDefaults
│   │   ├── objects/           # furniture.tsx / agents.tsx
│   │   ├── scene/             # environment.tsx
│   │   ├── systems/           # cameraLighting.tsx / sceneRuntime.tsx
│   │   └── avatars/           # profile.ts（已从 Claw3D 抄）
│   ├── sim/                   # agentStore.ts / tick.ts / roleMap.ts
│   ├── net/                   # api.ts / visualizationSocket.ts（事件契约，只读）
│   └── screens/               # OfficeScene.tsx / Dashboard.tsx
├── public/office-assets/models/furniture/  # 17 个 GLB 模型
└── vite.config.ts             # base=/3d/, outDir=../app/static/3d
```

---

## 2. 差距诊断（为什么说 coffee 落后 ~85%）

coffee 是 Claw3D retro-office 的「纯渲染内核移植版」，代码量仅约 11%（~2,000 行 vs 17,614 行）。`./3D.MD` 明确规划"只移植渲染内核 + 简化 tick"——这是**有意的架构裁剪**，不是偷工减料。但现在要全面追平。

| 模块 | Claw3D（完整） | coffee（现状） | 缺口 |
|------|----------------|----------------|------|
| core/navigation | 517 行 + 6 房间路由 | 简化 A* | 房间路由、高级特性 |
| objects/agents | 1248 行（18 refs，6 训练动画） | ~690 行基本表情 | 训练动画、手持物、完整表情 |
| objects/furniture | 755 行（InstancedMesh） | 143 行单件 | 实例化、动态杂物、高亮 |
| objects/machines | 2113 行（20+ 程序化机器） | ❌ 无 | 全缺 |
| scene/environment | 1049 行（多区域/画框/国旗） | 60 行单地板墙 | 装饰全缺 |
| systems/cameraLighting | 369 行（3 视角+跟随+昼夜） | 33 行固定光 | 视角系统全缺 |
| systems/NavigationSystem | 116 行（碰撞响应） | ❌ 无 | 全缺 |
| systems/visualSystems | 277 行（热力图/轨迹/名牌） | 仅名牌 | 调试系统全缺 |
| sim/tick | 434 行完整状态机 | 简化版 | bump/away/dance/社交全缺 |

---

## 3. 追平边界（禁区 — 明确不搬）

下列属于 Claw3D 特有业务，**不属于 3D 能力范畴，不追平**：

- ❌ `gateway` / `Hermes` / `demo-gateway` / Skills Marketplace / onboarding
- ❌ district 三层堆叠（本地 + 城市路径 + 远程办公室）—— coffee 是**单咖啡厅**
- ❌ `RetroOffice3D.tsx` 7248 行业务外壳（agent 编排/技能/任务 board）
- ❌ Claw3D 的 100+ 业务 props 接口
- ❌ gym 健身器材 / QA 测试台 / 服务器机柜 / 乒乓桌（咖啡厅用不到）
- ❌ 国旗程序化绘制（`UsaFlagArt`/`BrazilFlagArt`）

✅ **要追平**：core 算法 / objects 模型 / scene 环境 / systems 相机光照 / sim 模拟 / 交互编辑 / 调试工具 / Agent 人偶。

> **适配原则**：沉浸式覆盖层等"点击家具进全屏"保留交互模式，但**内容改为咖啡厅业务**（订单/库存/收银），不照搬 Claw3D 的 VSCode 模拟。

---

## 4. 分阶段 Roadmap（核心 — 按 Phase 顺序执行）

> 排序遵循依赖关系：core 基础 → 模拟（依赖 core）→ 相机（独立）→ 交互（依赖相机 raycaster）→ 模型场景 → Agent 人偶 → 可选高级

### Phase 0 — 基线与脚手架（半天）

**目标**：建立可量化对比基线。

- [ ] 记录 coffee 当前 `npm run build` 产物大小、首屏 fps、家具/agent 数量上限
- [ ] `frontend/src/office3d/` 下对照 Claw3D 补齐子目录骨架（若缺）：`systems/`、`overlays/`
- [ ] 由 Owner 主导建 git 分支（执行 Agent 不擅自建）
- **验证**：`cd frontend && npm run dev` 跑通现有咖啡厅，截图存档作"补齐前"对照

---

### Phase 1 — Core 渲染内核增强（1-2 天）

**目标**：core 层从"够用"升级到"完整"，为后续打基础。

| 来源（Claw3D 绝对路径） | 目标（coffee 相对路径） | 工作项 |
|------------------------|------------------------|--------|
| `Claw3D-main\src\features\retro-office\core\geometry.ts` | `frontend\src\office3d\core\geometry.ts` | 扩展 `ITEM_FOOTPRINT` 从 24 → 39 种家具尺寸；补全 `ITEM_METADATA` 阻塞规则 |
| `Claw3D-main\src\features\retro-office\core\persistence.ts` | `frontend\src\office3d\core\persistence.ts`（**新建**） | `saveFurniture/loadFurniture` localStorage 持久化 + namespace 支持 |
| `Claw3D-main\src\features\retro-office\core\furnitureDefaults.ts`（迁移思路） | 同名文件 | 借鉴签名比对迁移（`createFurnitureSignature`），为布局升级做平滑迁移 |

> **不搬**：`core/district.ts`（多区域）、6 个房间路由（gym/qa/server/phone/sms——咖啡厅无这些房间）。

**验证**：`npm run build` 通过；家具尺寸表扩充后现有咖啡厅布局不变形。

---

### Phase 2 — 模拟生动性 ⭐ 性价比最高（2-3 天）

**目标**：让 Agent 不再穿模——有碰撞、会休息、会走动。

| 来源（Claw3D） | 目标（coffee） | 工作项 |
|----------------|----------------|--------|
| `systems\NavigationSystem.tsx`（116 行） | `frontend\src\office3d\systems\NavigationSystem.tsx`（**新建**） | **整体移植** `applyAgentCollisionBumps`：空间哈希桶 + 分离力 + 逃逸方向 + 冻结气泡；**去掉 janitor 特判** |
| `RetroOffice3D.tsx` 的 `useAgentTick`（1751-2193 行） | `frontend\src\sim\tick.ts`（扩展） | tick 末尾调 `applyAgentCollisionBumps`；补 **away 状态**（15 分钟未活动→躺 couch/beanbag 半透明）、**dance**（`danceUntilByAgentId` 驱动）、**社交随机走**（0.5% 概率走社交家具） |
| `core\types.ts` 的 RenderAgent 字段 | `frontend\src\office3d\core\types.ts` | 补 `bumpedUntil`/`bumpTalkUntil`/`collisionCooldownUntil`/`separationReplanAt`/`awayUntil`/`danceUntil` |
| `RetroOffice3D.tsx` 状态映射 | `frontend\src\sim\agentStore.ts` | applyEvent 支持 dance/away 触发；speech Map 支持 bumpTalk |

**适配点**：coffee 的 `ROAM_POINTS` 按咖啡厅三大区域（吧台/座席/休闲）重定义，参考 `furnitureDefaults.ts` 布局。

**验证**：两 agent 相向行走→碰撞冻结+各逃逸+气泡；agent 长时 idle→自动去沙发躺下（半透明 + z z z 气泡）。

---

### Phase 3 — 相机与视角（2-3 天）

**目标**：从"只能 OrbitControls 转圈"升级到"多视角预设 + 跟随聚焦 + 点击地面"。

| 来源（Claw3D） | 目标（coffee） | 工作项 |
|----------------|----------------|--------|
| `systems\cameraLighting.tsx` 的 `CAMERA_PRESETS` + `CameraAnimator` | `frontend\src\office3d\systems\cameraLighting.tsx`（扩展） | 咖啡厅 3 视角：**overview 全景** / **barCounter 吧台特写** / **lounge 休闲区**；lerp 过渡（pos 0.06 / target 0.06 / zoom 0.08） |
| `systems\cameraLighting.tsx` 的 `FollowCamController` | 同上 | 点 agent 切 PerspectiveCamera（65 FOV），球坐标拖拽+滚轮缩放（0.8~10），离开还原 |
| `systems\sceneRuntime.tsx` 的 `FloorRaycaster` | `frontend\src\office3d\systems\sceneRuntime.tsx`（扩展） | 指针→地面平面投影，支持 `onMove`/`onClick`（Phase 4 编辑器要用） |
| `systems\cameraLighting.tsx` 的 `DayNightCycle` | 同上（**可选**） | 300s/6 关键帧昼夜。coffee 主动删过（嫌暗），若加回需**调亮夜间 keyframe** |

**关键决策**：**保留 OrbitControls 作为默认自由浏览**，FollowCam 仅在"聚焦某 agent"时激活，两者并存（比 Claw3D 更优）。

**验证**：UI 加视角切换按钮→相机平滑过渡；点 agent→跟随相机可拖拽；点空地→raycaster 回调（控制台打印坐标）。

---

### Phase 4 — 交互编辑能力（3-4 天）

**目标**：用户能编辑咖啡厅布局——拖拽、选中、键盘、放置。

| 来源（Claw3D） | 目标（coffee） | 工作项 |
|----------------|----------------|--------|
| `objects\furniture.tsx` 的 `isSelected/isHovered` emissive | `frontend\src\office3d\objects\furniture.tsx`（扩展） | FurnitureModel 加 `isSelected`/`isHovered` props，选中黄光/悬停蓝光 emissive 高亮 |
| `RetroOffice3D.tsx` 的 PALETTE（307-420 行） | `frontend\src\screens\OfficeScene.tsx` + 新建 `ui\Palette.tsx` | 27 种可放置家具面板；点击进入 placing 模式 + `PlacementGhost` 预览 |
| `RetroOffice3D.tsx` 的 `handleFurniturePointerDown/Over/Out` | `OfficeScene.tsx` | editMode 下选中+拖拽（drag: idle/placing/moving）；依赖 Phase 3 FloorRaycaster |
| `RetroOffice3D.tsx` 键盘快捷键（4942-5023） | `OfficeScene.tsx` | Arrow 移动 / PageUp-Down 抬升 / `[ ]` 旋转 / Delete 删除 / Esc 退出 |
| `RetroOffice3D.tsx` 的 `createWallItem` + `wallDrawStart` | `OfficeScene.tsx` | 墙体两点绘制（`createWallItem` 已在 `core\geometry.ts`，接线即可） |
| `objects\furniture.tsx` 的 `PlacementGhost` | `frontend\src\office3d\objects\furniture.tsx` | 放置预览半透明幽灵 |

**验证**：进编辑模式→拖 PALETTE 家具→空地放置→选中拖动→键盘旋转/抬升→Delete 删除→Esc 退出；刷新后布局持久化（依赖 Phase 1 persistence）。

---

### Phase 5 — 模型与场景丰富度（4-6 天，工作量最大）

**目标**：从"只有 GLB 家具"升级到"程序化机器 + 实例化 + 装饰 + 沉浸式覆盖层"。

#### 5a. 程序化机器模型（从 `objects\machines.tsx` 2113 行**选择性**移植）

coffee 是咖啡厅，**只搬业务相关机器**：

| 组件 | 搬 | 咖啡厅用途 |
|------|:--:|-----------|
| `AtmMachineModel`（收银/ATM） | ✅ | 收银台自助点单机 |
| `VendingMachineModel`（售货机，kitchen.tsx） | ✅ | 咖啡豆/零食售货 |
| `JukeboxModel`（点唱机，228 行） | ✅ | 咖啡厅背景音乐（旋转黑胶） |
| `StoveModel`/`MicrowaveModel`/`WallCabinetModel`/`SinkModel`（kitchen.tsx） | ✅ | 吧台后厨 |
| `PingPongTableModel` + 健身器材系列 | ❌ | 咖啡厅不需要 |
| `QaTerminalModel`/`DeviceRackModel`/`TestBenchModel` | ❌ | 非咖啡厅业务 |

**目标**：`frontend\src\office3d\objects\machines.tsx`（**新建**，~600 行精选）。

#### 5b. InstancedMesh 家具优化

| 来源 | 目标 | 工作项 |
|------|------|--------|
| `objects\furniture.tsx` 的 `InstancedFurnitureItems` + `buildFurnitureItemMatrix` | `frontend\src\office3d\objects\furniture.tsx`（扩展） | 同类家具合并 InstancedMesh，按 instanceId 反查 _uid 支持点击。家具多时性能显著提升 |

#### 5c. 场景装饰（从 `scene\environment.tsx` 1049 行移植）

| 来源组件 | 目标 | 工作项 |
|---------|------|--------|
| `WallPictures` + `FramedPicture` | `frontend\src\office3d\scene\environment.tsx`（扩展） | 咖啡厅墙画/菜单板（程序化绘制，内容改为咖啡品类/价目） |
| 城市路灯/花园灯（球形 emissive） | 同上 | 咖啡厅氛围灯（吧台/休闲区点缀） |
| `DoorModel`（动态开门，primitives.tsx） | `frontend\src\office3d\objects\primitives.tsx`（**新建**） | 咖啡厅入口门自动开合 |
| `UsaFlagArt`/`BrazilFlagArt`/城市花坛/草地 | ❌ | 非咖啡厅风格 |

#### 5d. 沉浸式覆盖层（从 `overlays\MonitorImmersiveContent.tsx` 471 行适配）

| 来源 | 目标 | 工作项 |
|------|------|--------|
| 沉浸式覆盖层框架（ESC 关闭、全屏切换） | `frontend\src\overlays\`（**新建**） | 点收银台→进订单详情面板；点咖啡机→进库存/制作面板。**内容改为咖啡厅业务**，不照搬 VSCode |

**验证**：场景出现收银机/售货机/点唱机；InstancedMesh 后 fps 提升；墙有咖啡菜单画；点收银台进全屏订单面板。

---

### Phase 6 — Agent 人偶增强（2-3 天）

**目标**：从"基本表情盒状人偶"升级到"完整表情系统 + 动画 + 手持物"。

| 来源（Claw3D `objects\agents.tsx` 1248 行） | 目标（coffee `objects\agents.tsx`） | 工作项 |
|---------------------------------------------|--------------------------------------|--------|
| 18 个骨骼 ref + useFrame 动画体系 | 同名文件（扩展） | 补全身体倾斜/bounce/breat/手臂腿摆动公式 |
| 6 种 workoutStyle 动画 | **选择性** | 咖啡厅只保留 `stretch`（拉伸）+ 基础走路，不搬 run/bike/box |
| 完整表情系统 | 扩展 | 4 种眉毛位置 + 嘴角微笑/苦笑 + 说话脉冲 + 眨眼周期随状态变 |
| 手持物（heldPaddle/heldCleaningTool 等） | **选择性** | 咖啡师手持咖啡杯/托盘（**新建** `heldCoffeeCup` 几何） |
| Away 半透明 + z z z 气泡 | 扩展 | 配合 Phase 2 away 状态 |
| 脉冲圈（working 绿/error 红） | 扩展 | 补全 bell 曲线（`sin(progress*π)`）|

**验证**：咖啡师 working 绿圈脉冲+眯眼皱眉；error 红圈+怒眉；说话嘴部脉冲；idle 偶尔眨眼。

---

### Phase 7 — 可选高级特性（按需，1-2 天）

| 来源 | 目标 | 价值 |
|------|------|------|
| `systems\visualSystems.tsx` 的 `HeatmapSystem` | `frontend\src\office3d\systems\visualSystems.tsx`（**新建**） | 调试 agent 行为热区（开发期有用） |
| 同上 `TrailSystem` | 同上 | 行走轨迹可视化 |
| `AdaptiveDprController` | `OfficeScene.tsx` | 帧率自适应降 DPR（性能优化） |

---

## 5. coffee 侧文件清单（新增/修改总览）

**新建（7 项）：**
- `frontend/src/office3d/core/persistence.ts`
- `frontend/src/office3d/systems/NavigationSystem.tsx`
- `frontend/src/office3d/systems/visualSystems.tsx`（可选，Phase 7）
- `frontend/src/office3d/objects/machines.tsx`
- `frontend/src/office3d/objects/primitives.tsx`
- `frontend/src/overlays/`（沉浸式覆盖层）
- `frontend/src/ui/Palette.tsx`（编辑器面板）

**扩展（10 项）：**
- `frontend/src/office3d/core/geometry.ts`（footprint 扩充）
- `frontend/src/office3d/core/types.ts`（RenderAgent 字段）
- `frontend/src/office3d/objects/furniture.tsx`（InstancedMesh + 高亮 + Ghost）
- `frontend/src/office3d/objects/agents.tsx`（表情 + 动画 + 手持物）
- `frontend/src/office3d/scene/environment.tsx`（装饰）
- `frontend/src/office3d/systems/cameraLighting.tsx`（多视角 + 跟随）
- `frontend/src/office3d/systems/sceneRuntime.tsx`（FloorRaycaster）
- `frontend/src/sim/tick.ts`（碰撞 + away + dance + 社交）
- `frontend/src/sim/agentStore.ts`（状态机扩展）
- `frontend/src/screens/OfficeScene.tsx`（编辑器接线）

---

## 6. 端到端验证清单（每 Phase 完成后勾选）

- [ ] **Phase 0**：`npm run build` 通过，截图存档基线
- [ ] **Phase 1**：家具尺寸表扩充后现有咖啡厅布局无变形
- [ ] **Phase 2**：两 agent 相向碰撞→冻结+逃逸+气泡；agent 长时 idle→躺沙发半透明
- [ ] **Phase 3**：3 视角切换平滑过渡；点 agent→跟随相机可拖拽；点空地→raycaster 触发
- [ ] **Phase 4**：编辑模式拖放家具→选中→键盘旋转/抬升→删除→刷新持久化
- [ ] **Phase 5**：收银机/售货机/点唱机出现；InstancedMesh 后 fps 提升；墙菜单画；点收银台进订单面板
- [ ] **Phase 6**：咖啡师 working 绿圈/说话嘴部脉冲/眨眼；error 红圈怒眉
- [ ] **Phase 7**：热力图/轨迹可切换；低帧自动降 DPR
- [ ] **全程守恒**：ws 事件契约不破坏；后端 `/chat`/`/admin/restaurant-state` 未受影响；`tsc --noEmit` 零错误

---

## 7. 风险与注意事项

1. **不要一次性整体移植 `RetroOffice3D.tsx`**——7248 行业务胶水，只能逐函数/逐组件按 Phase 拆解。
2. **角色映射不同**：Claw3D 角色（agent 编排）≠ coffee 角色（咖啡师/收银/服务员/主管/访客）。表情/动画可搬，但状态触发逻辑要按 coffee 的 `roleMap.ts` + ws 事件重接。
3. **RoamPoints/目标点重定义**：Claw3D 按其布局，coffee 必须按咖啡厅三大区域（吧台/座席/休闲）重定义。
4. **保留 OrbitControls**：FollowCam 作为聚焦增强叠加，不替换 OrbitControls。
5. **machines.tsx 选择性移植**：只搬业务相关机器，省 60% 工作量。
6. **性能基线**：每加 system 量 fps；InstancedMesh 和碰撞响应是性能重点。
7. **改后端契约前**先读 `frontend/src/net/api.ts` 顶部注释。
8. **已知移植残留**（来自 `frontend/CLAUDE.md`，非本次引入，留意不要加剧）：navigation.ts 的 `ENTRY_POINT/ROAM_POINTS/ITEM_FOOTPRINT/snap` 部分 `void` 占位；roleMap 注释 "1800x1800" 与实际 `CANVAS_H=720` 不符。

---

## 8. 进度记录（执行 Agent 每完成一 Phase 填写）

| Phase | 状态 | 完成日期 | 执行 Agent | 产物/PR | 备注 |
|-------|:----:|---------|-----------|---------|------|
| 0 基线 | ⬜ 待执行 | | | | |
| 1 Core | ⬜ 待执行 | | | | |
| 2 模拟 | ⬜ 待执行 | | | | |
| 3 相机 | ⬜ 待执行 | | | | |
| 4 交互 | ⬜ 待执行 | | | | |
| 5 模型场景 | ⬜ 待执行 | | | | |
| 6 Agent 人偶 | ⬜ 待执行 | | | | |
| 7 高级可选 | ⬜ 待执行 | | | | |

> 状态图例：⬜ 待执行 ｜ 🔄 进行中 ｜ ✅ 完成 ｜ ⚠️ 阻塞

---

**执行 Agent 自检**：开工前确认你已读完第 0.2 节的 8 个必读文件，并理解第 0.3 节的 10 条铁律。有任何歧义先问 Owner，不要猜。
