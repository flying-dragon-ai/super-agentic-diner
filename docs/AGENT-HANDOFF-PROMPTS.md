# Agent 派活启动 Prompt 模板

> 📌 本文件提供**可直接复制粘贴**的启动 prompt，用于把 `3D-ALIGNMENT-ROADMAP.md` 和 `SKILL-VISUALIZATION-ROADMAP.md` 派给**干净上下文的执行 Agent**。
>
> 使用方式：在新 Agent 会话里，整段复制对应 prompt 即可。每个 prompt 都自包含——Agent 不需要本会话任何历史。

---

## 🎯 整体策略（先看这个）

两份 roadmap 有依赖关系：

```
SKILL-VISUALIZATION（事件通）  ──►  3D-ALIGNMENT（渲染丰富）
        ↑ 必须先做                      ↑ 后做
   不通这个, 3D 再漂亮也是死的      事件通了才有意义去美化
```

**建议**：先派一个 Agent 干 SKILL-VISUALIZATION（5 Phase，约 3-5 天），验收通过后再派 Agent 干 3D-ALIGNMENT（7 Phase，约 15-20 天）。

也可以两份**并行**派（SKILL 的 Phase 1 前端契约 + 3D 的 Phase 1 core 内核不冲突），但 **3D 的 Phase 2+（碰撞/相机/模型）依赖 SKILL 通了才能验证效果**，所以并行价值有限。

---

## Prompt A — 执行 SKILL-VISUALIZATION-ROADMAP（建议先派）

```
你是一个资深全栈工程师，负责实施一个已规划好的功能。请严格按照规划文档执行，不要自由发挥。

## 你的任务

打通「外部 Agent 工具通过 Skill 接入 → 注册 → 可视化新增人物 → 下单时服务员联动动作」这条链路。

完整规划文档在：
D:\temp\EVOMAP\coffee-ai-boss\docs\SKILL-VISUALIZATION-ROADMAP.md

## 执行要求

1. **第一步：完整阅读** `docs\SKILL-VISUALIZATION-ROADMAP.md`，理解：
   - 第 0.2 节的 10 个必读文件（逐个读，建立上下文）
   - 第 0.3 节的 10 条操作铁律（违反一条返工）
   - 第 2 节的 5 个契约 Bug（B1-B5）
   - 第 4 节的 Phase 1-5 roadmap 和服务员编排时序表

2. **严格按 Phase 顺序执行**：Phase 1（前端契约适配）→ Phase 2（服务员团队）→ Phase 3（编排联动）→ Phase 4（snapshot）→ Phase 5（文档）。Phase 1 是地基，必须先做。

3. **每完成一个 Phase**：
   - 按第 6 节验证清单逐条验证
   - 在第 9 节进度记录表填写状态/日期
   - 跑 `tsc --noEmit`（前端）确认零类型错误
   - 汇报本次 Phase 的改动文件和验证结果

4. **铁律**（摘自文档第 0.3 节，必须遵守）：
   - 路径用双引号包裹（Windows 环境）
   - ws 事件 role/action 集合只读，只新增 staff 编排事件，不删改现有
   - 前端只做"读取适配"，编排逻辑全后端
   - 不动 order/User/SkillOrderLedger 等业务表结构
   - 不改 /chat、/admin/restaurant-state、订单支付业务
   - 改前先 Read 文件理解上下文
   - 不擅自 git 提交

5. **遇到歧义**：先问我，不要猜。

## 验收标准

- Phase 3 完成后：CLI 跑 `python .agents\skills\a2a-super-order\scripts\order.py --message "一杯拿铁"`，3D 页面能看到完整联动——顾客入场 → 服务员走向收银台 → 收银员收银 → 咖啡师做咖啡（绿圈脉冲）→ 服务员送餐，全程与 /visualization/events 一一对应。

现在开始：先读规划文档和 10 个必读文件，然后告诉我你的执行计划（准备先动哪些文件、预计每个 Phase 的工作量），等我确认后再动手改代码。
```

---

## Prompt B — 执行 3D-ALIGNMENT-ROADMAP（SKILL 验收后派）

```
你是一个资深前端/3D 图形工程师，负责把一个 3D 场景从"能跑的简化版"升级到 Claw3D 级别的沉浸感。

## 你的任务

把 Claw3D-main 的 3D 渲染能力全面移植/对齐到 coffee-ai-boss 前端。

完整规划文档在：
D:\temp\EVOMAP\coffee-ai-boss\docs\3D-ALIGNMENT-ROADMAP.md

## 前置条件

另一份文档 `docs\SKILL-VISUALIZATION-ROADMAP.md` 的事件链路应该已经打通（顾客下单能驱动服务员动作）。你在这个基础上做渲染丰富度。开工前先确认：3D 场景能正常显示、ws 事件能驱动人偶。如果事件链路没通，先停下来告诉我。

## 执行要求

1. **第一步：完整阅读** `docs\3D-ALIGNMENT-ROADMAP.md`，理解：
   - 第 0.2 节的 8 个必读文件（含 Claw3D 来源）
   - 第 0.3 节的 10 条操作铁律
   - 第 3 节的禁区（不搬 gateway/远程办公室/district/gym 等）
   - 第 4 节的 Phase 0-7

2. **严格按 Phase 顺序**：Phase 0（基线）→ 1（core）→ 2（模拟）→ 3（相机）→ 4（交互）→ 5（模型场景）→ 6（Agent 人偶）→ 7（可选高级）。

3. **核心策略**：数据驱动 + 逐组件移植。绝不整体复制 Claw3D 的 RetroOffice3D.tsx（7248 行业务胶水），只搬纯 3D 能力。来源文件绝对路径都在文档第 4 节的表格里。

4. **每完成一个 Phase**：
   - 按第 6 节验证清单验证
   - 第 8 节进度记录表填状态
   - 量 fps（性能基线，每加一个 system 都要测）
   - 汇报改动文件

5. **铁律**：
   - 路径用双引号包裹
   - 不搬 Claw3D 的 gateway/Hermes/远程办公室/district/业务外壳
   - machines.tsx 选择性移植（咖啡厅不需要健身器材/QA，只搬收银机/售货机/点唱机/厨房）
   - 保留 OrbitControls，FollowCam 作为聚焦增强叠加
   - 代码注释英文（跟随现有文件）
   - 改前先 Read
   - 不擅自 git 提交

6. **遇到歧义**：先问我。

## 验收标准

- Phase 6 完成后：3D 咖啡厅有 Agent-Agent 碰撞响应、多视角相机+跟随、家具编辑器、程序化收银机/点唱机、墙菜单画、咖啡师完整表情动画。fps 稳定。

现在开始：先读规划文档和 8 个必读文件，然后告诉我执行计划，等我确认后再动手。
```

---

## 使用小贴士

1. **派活后让 Agent 先汇报计划**：两个 prompt 结尾都要求 Agent"先读文档 + 汇报执行计划，等确认再动手"。这样你能**在它瞎改前纠偏**，比让它直接闷头干安全得多。

2. **验收节点**：
   - Prompt A 的验收点 = Phase 3 跑通完整下单联动
   - Prompt B 的验收点 = Phase 6 完成所有渲染增强
   - 中途每个 Phase 都要它填进度表 + 汇报

3. **如果 Agent 跑偏**：直接引用文档章节号纠正——"回去看 SKILL-VISUALIZATION-ROADMAP.md 第 0.3 节铁律第 3 条"。

4. **并行派活的注意**：若两份同时派，**明确划分文件所有权**——SKILL Agent 动 `frontend/src/screens/OfficeScene.tsx` + `sim/*` + `app/services/*`；3D Agent 动 `office3d/*`（core/objects/scene/systems）。**OfficeScene.tsx 是冲突高发区**（两份都要改），最好串行，或约定 SKILL 先改完再交给 3D。

5. **换工具派活**：这两个 prompt 是中文（因 roadmap 是中文），Claude Code / Codex / Cursor / Trae 都能读。Codex 偏好英文可让 Agent 自行翻译执行，不影响。
