# Agent 派活启动 Prompt 模板（v2，复核修正版）

> 📌 本文件提供**可直接复制粘贴**的启动 prompt。
> **v2 修正（2026-06-20 复核后）**：原 v1 基于"两份 roadmap 都待执行"，**与实际严重不符**——已大幅实施。Prompt 已从"实施"改为"验证 / 盘点接力"。

---

## ⚠️ 派活前必读：两份 roadmap 的真实状态（2026-06-20 复核确认）

| Roadmap | 实施状态 | 证据 | 还差什么 |
|---------|---------|------|---------|
| **SKILL-VISUALIZATION** | ✅ **5 Phase 全完成** | 该文档第 9 节（Codex 实施记录）+ 第 10 节（第二 Agent 独立验证 PASS + 真实 Skill 端到端单 22 事件/9 staff 编排）| 仅付费单（第 3 单起）因 `EVOMAP_API_KEY` 占位符未跑通——**运维配置**，非代码 |
| **3D-ALIGNMENT** | 🟡 **部分完成** | coffee `office3d/` 已有：Phase 2 碰撞(`NavigationSystem.tsx`)、Phase 3 相机(`CameraAnimator`/`FollowCamController`)、Phase 5a 机器(`Atm`/`Vending`/`Jukebox`)、Phase 7 调试(`Heatmap`/`Trail`)| Phase 1(persistence 内容待确认)、**Phase 4(交互编辑器，未见 ui/ 目录，疑似未做)**、**Phase 6(Agent 人偶增强，待确认)**；且第 8 节进度记录**未回填**（全显示待执行）|

> **关键**：别再派 Agent "实施 SKILL"或"全面移植 3D"——会重做已完成的工作。下方 Prompt 已改为"验证/盘点接力"。

---

## 🎯 派活策略（v2）

```
SKILL-VISUALIZATION ──► 已完成，派 Agent 做「独立验证 + 付费单配置收尾」
3D-ALIGNMENT ─────────► 部分完成，派 Agent 做「盘点已做 + 接力未做(Phase 4/6) + 回填进度记录」
```

两份任务**互不阻塞**，可并行派（文件所有权不冲突：SKILL 验证动后端配置 + 运行时；3D 盘点动前端 office3d）。

---

## Prompt A — SKILL 独立验证 + 付费单收尾

```
你是一个资深全栈工程师。注意：本任务【不是实施】，而是【独立验证已实施的功能 + 收尾一个运维配置项】。不要重写已有代码。

## 背景

crossroads-agent-cafe 的「Skill 接入可视化联动」功能已被前一位 Agent（Codex）实施完成 5 个 Phase，并有第二位 Agent 做过独立验证（见文档第 10 节）。你的任务是【第三方独立复核】+ 补齐唯一未覆盖项。

规划文档：D:\temp\EVOMAP\coffee-ai-boss\docs\SKILL-VISUALIZATION-ROADMAP.md
（重点读第 9 节进度记录 + 第 10 节验证证据，了解已做了什么）

## 你的任务

1. **独立运行时验证**（复跑第二 Agent 的验证，确认无回归）：
   - 启动后端：cd D:\temp\EVOMAP\coffee-ai-boss && python -m uvicorn app.main:app --port 8000
   - 启动前端：cd frontend && npm run dev
   - 确认 GET /agents 含 4 个 staff:barista/cashier/waiter/manager
   - 连 ws /ws/visualization，确认 scene.snapshot.payload.agents 含 4 staff
   - CLI 下单：python .agents\skills\a2a-super-order\scripts\order.py --message "一杯拿铁"
   - 确认完整联动：顾客入场→服务员走向收银台→收银员收银→咖啡师做咖啡(绿圈)→服务员送餐
   - 按 SKILL 文档第 6 节验证清单逐条核对

2. **若发现回归**（前两轮验证 PASS 但现在坏了）：最小化修复，不重构。修完重跑验证。

3. **付费单收尾**（唯一未覆盖项，属运维配置）：
   - 当前 .trae/.zhipu/.qingyan/.codex 的 EVOMAP_API_KEY 全是 "your-api-key-here" 占位符
   - 向 Owner 索要真实 EvoMap 凭证（API_KEY + node_id + node_secret + service_listing_id）
   - 配置后跑第 3 单（超过免费额度），确认 EvoMap 积分扣费链路端到端通
   - 若 Owner 暂不提供凭证，在文档第 10 节"仍未覆盖项"记录待办，不强求

4. **铁律**：
   - 路径用双引号包裹（Windows）
   - 不重写 staff_service.py / OfficeScene.tsx 等已实施代码（除非发现明确 bug）
   - ws 事件 role/action 集合只读
   - 不动 order/User/SkillOrderLedger 业务表
   - 改前先 Read；不擅自 git 提交

5. **交付**：在 SKILL 文档第 10 节追加你的独立验证记录（验证手段 + 结果 + 日期），与已有两条记录并列。

## 遇到歧义先问 Owner，不要猜。
```

---

## Prompt B — 3D 盘点 + 接力未做 Phase

```
你是一个资深前端/3D 工程师。注意：本任务【不是从零移植】，而是【先盘点已实施到哪，再接力未做的部分】。绝不重写已存在的文件。

## 背景

crossroads-agent-cafe 的 3D 渲染追平 Claw3D 工程已【部分完成】——coffee 的 office3d/ 下已有多个本该"新建"的文件（machines.tsx/NavigationSystem.tsx/visualSystems.tsx/primitives.tsx/persistence.ts），对应 3D-ALIGNMENT 的多个 Phase 已被前一位 Agent 实施。但文档第 8 节进度记录还全显示"待执行"，且部分 Phase 是否做完不明。

规划文档：D:\temp\EVOMAP\coffee-ai-boss\docs\3D-ALIGNMENT-ROADMAP.md
来源参考：D:\temp\EVOMAP\Claw3D-main\src\features\retro-office\（Claw3D 原始实现，用于对照）

## 你的任务

1. **先盘点**（动手改代码前必做）：逐 Phase 核对 coffee office3d/ 实际代码 vs roadmap 第 4 节要求，判定每 Phase 状态：
   - 已确认实施（复核证据）：Phase 2 碰撞(NavigationSystem.tsx:18 applyAgentCollisionBumps)、Phase 3 相机(cameraLighting.tsx CameraAnimator@84/FollowCamController@133)、Phase 5a 机器(machines.tsx Atm@27/Vending@73/Jukebox@121)、Phase 7 调试(visualSystems.tsx Heatmap@16/Trail@76)
   - **待你确认**：Phase 1(persistence.ts 内容是否完整)、Phase 4(交互编辑器——找 ui/Palette.tsx，疑似未做)、Phase 6(Agent 人偶增强——对照 Claw3D agents.tsx 看 coffee agents.tsx 表情/动画/手持物完整度)

2. **回填进度记录**：把盘点结果写进 3D 文档第 8 节（状态 ✅完成/🟡部分/❌未做 + 完成日期 + 产物），消除"全待执行"的误导。学 SKILL 文档第 9 节的格式。

3. **接力未做的 Phase**（盘点确认后才动手）：
   - 重点疑似未做：Phase 4（家具编辑器 PALETTE + 拖拽 + 键盘快捷键）、Phase 6（咖啡师完整表情/动画/手持咖啡杯）
   - 来源绝对路径都在 3D 文档第 4 节表格（Claw3D retro-office 对应文件，已复核行号准确）
   - 绝不重写已存在的 machines.tsx/NavigationSystem.tsx 等——只扩展或新建缺失的

4. **铁律**：
   - 路径用双引号包裹
   - 绝不整体复制 Claw3D RetroOffice3D.tsx（7248 行业务胶水）
   - 不搬 gateway/Hermes/远程办公室/district/gym（见 3D 文档第 3 节禁区）
   - 保留 OrbitControls，FollowCam 作聚焦增强叠加
   - 代码注释英文；改前先 Read；不擅自 git 提交
   - 每加 system 量 fps

5. **验收**：盘点表回填 + 未做 Phase 实施完毕 + npm run build 通过 + fps 稳定。

## 遇到歧义先问 Owner，不要猜。特别是盘点时若发现某 Phase 状态与预期不符，先报告再决定动作。
```

---

## 使用小贴士（v2）

1. **派活前先看各 roadmap 的进度记录**（SKILL 第 9/10 节、3D 第 8 节），别凭本文件顶部的摘要就下结论——进度记录是 ground truth。

2. **让 Agent 先盘点/验证再动手**：两个 prompt 都要求 Agent 先核对现状、汇报发现，等确认才改代码。这能在它瞎改前纠偏。

3. **验收节点**（v2 更新）：
   - Prompt A = 独立验证无回归 + 付费单配置（或记录待办）
   - Prompt B = 盘点表回填 + Phase 4/6 接力完成

4. **文件所有权**（v2，两份可并行）：
   - Prompt A 动：后端配置(.env / MCP 配置) + 运行时验证，基本不碰代码
   - Prompt B 动：frontend/src/office3d/* + 可能的 ui/
   - 无冲突，可同时派

5. **若 Agent 报告"发现某功能已存在"**：这是正常的（本就部分实施了），让它转入"验证/扩展"模式，别让它"重写以求统一"。

6. **换工具派活**：prompt 是中文（roadmap 中文），Claude Code/Codex/Cursor/Trae 都能读。

---

## 附：v1 → v2 变更说明

| 项 | v1（已废弃）| v2 |
|----|------------|-----|
| 前提假设 | 两份 roadmap 都待执行 | 两份都已大幅实施 |
| Prompt A | 实施 SKILL 5 Phase | 独立验证 + 付费单收尾 |
| Prompt B | 全面移植 3D | 盘点 + 接力未做 Phase |
| 并行策略 | 有冲突（OfficeScene 高发）| 无冲突，可并行 |
| 风险 | 误导 Agent 重做已完成工作 | 基于真实状态，聚焦增量 |
