# 3D 咖啡厅编辑器完整度对齐 Claw3D

> 状态：**已实施**（2026-06-20）。构建通过（`tsc --noEmit && vite build`）。
> 改动文件：`frontend/src/screens/OfficeScene.tsx`、`frontend/src/ui/SelectedObjectPanel.tsx`（新建）。
> 对照源：`D:\temp\EVOMAP\Claw3D-main\src\features\retro-office\RetroOffice3D.tsx`。

## 背景

用户反馈：3D 咖啡厅场景（`/3d/scene`）的家具编辑器"看不到保存按钮，编辑后不生效"，并指出与 Claw3D 的完整度未完全对齐。系统对照移植源头 Claw3D 后确认：差距不止"保存"一项，而是编辑器整体完整度——保存机制、选中对象操作面板、操作封装、Machine 类对象的可编辑性四个层面都落后。

## 差距清单与实施

### P0 — 保存机制：debounced autosave（核心 bug）

**根因**：原 `OfficeScene.tsx` 用 6 处手动 `saveFurniture`，**漏了键盘移动/旋转/抬升 3 处** → 用键盘微调家具后 `localStorage` 不更新 → 刷新页面丢失，表现为"编辑后不生效"。

**修复**：移植 Claw3D `RetroOffice3D.tsx:3147-3154` 的单一 debounced autosave effect：

```ts
useEffect(() => {
  const id = window.setTimeout(() => saveFurniture(furniture), 300);
  return () => window.clearTimeout(id);
}, [furniture]);
```

删掉全部 6 处手动 `saveFurniture`（放置/拖动/删除/恢复默认）。现在 `saveFurniture` 全文件仅剩 effect 内一处——**任何来源的 furniture 变更都自动 300ms 后落盘**。Claw3D 本身也没有"保存"按钮，靠 autosave。

### P1 — 操作封装：`moveSelectedItem` / `rotateSelectedItem` / `updateSelectedItem`

移植 Claw3D `:4862-4895`。键盘 handler 和面板按钮共用同一组回调，两条输入路径永不分叉：

- `snap()` 网格吸附（`SNAP_GRID=10`）
- `normalizeDegrees()` 角度规范化到 `[0,360)`
- elevation clamp `[-0.4, 2.5]`（与 Claw3D 一致；原代码只限下限 0）
- `CANVAS_W/H` clamp 保留（防出界，Claw3D 无此保护，我们有界保留更安全）

### P1 — 可视化选中面板：新建 `ui/SelectedObjectPanel.tsx`

原选中面板只有纯文字快捷键提示 + 删除/恢复默认两按钮。移植 Claw3D `:6801-6927`（咖啡厅化、去 desk assignment）：

- 标题：类型 label（从 `PALETTE` 查）+ 实时 `rot X° · lift Y` 数值
- **Move 3×3 方向按钮网格**（↑前 / ←左 / 抬升 / 右→ / ↓后 / 下降）—— 鼠标可直接点
- **Rotate ±15° 按钮**
- 关闭 ✕ 按钮（P2）
- 删除 / 恢复默认（P2，恢复默认带 `window.confirm`）
- 快捷键提示文字（键盘仍可用）

> 选址保持 `bottom:12, left:192`，避免与右上工具栏/view 按钮挤。

### P2 — 关闭按钮 + Reset 防误触

- 选中面板 ✕ 按钮 + `closeSelectedEditor`（原来只能 Esc 取消选中）。
- "恢复默认布局"包 `window.confirm("恢复默认布局？当前所有编辑将丢失。")`，防一键误清空。

### 盲区修复 — Machine 类对象编辑模式下可选中

**根因**：`coffee_machine / atm / vending / jukebox` 经 `resolveMachine` 走 Machine 组件分支，其 `onClick` 原先恒走 `handleMachineActivate`，而后者在 `editMode` 直接 `return` → **编辑模式下点这 4 类对象无反应，不能选中/移动/旋转/删除**。

**修复**：Machine 的 `onClick` 改为 editMode-aware：

```tsx
onClick={() => editMode ? handleFurniturePointerDown(item._uid) : handleMachineActivate(item)}
```

Machine 组件本就具备 `SelectionRing`（选中金色发光环）+ `getMachineTransform`（位置绑定 `item.x/y`），所以选中后自动高亮、跟鼠标移动（FloorRaycaster 是"点击选中 → 鼠标移动跟手 → 点击空地落下"模式，`pointermove` 无需按住按钮）、可用 `SelectedObjectPanel` 编辑、可删除。

### 死代码清理

- 删除未使用的 `debug` state（`useState(false)`，从未读写）。
- 删除 `FurnitureModel` 的 `onPointerDown` 里针对 `coffee_machine` 的特判（`item.type === "coffee_machine" && !editMode`）——死代码，因为 `coffee_machine` 走 Machine 分支，永远到不了 FurnitureModel。

## 不移植（有意分化或不适用）

- **Desk Assignment 下拉**：无 desk 概念。
- **Space 键平移**：OrbitControls 已有右键平移。
- **后端 `PUT /api/office/layout` 远程同步**：Claw3D 多房间协作特性，单咖啡厅 localStorage 无需求。
- **PALETTE 条目**：已咖啡厅化定制（非差距）。
- **Edit Mode 徽章 / drawer toggle**：当前用按钮文字"✏️ 编辑中" + Palette 常显，属 UX 差异非功能缺失。

## 验证

**构建**：`cd frontend && npm run build` → `tsc --noEmit` 无类型错误，`vite build` 628 模块成功。

**手动端到端**（`npm run dev` → `/3d/scene`）：
1. 进编辑模式，选中家具/Machine → `SelectedObjectPanel` 出现，显示类型 + 实时 rot/lift。
2. **P0 回归**：方向键/PgUp/Dn/`[]` 微调 → **刷新页面改动保留**（修复前丢失）。
3. **P1 面板**：点 Move 3×3 / Rotate ±15° 按钮 → 对象响应，数值实时更新。
4. **盲区修复**：编辑模式下点咖啡机/ATM/售货机/点唱机 → 金色选中环 + 可拖动/编辑/删除（修复前无反应）。
5. **P2**：点 ✕ 关闭面板；"恢复默认"弹 confirm。
6. DevTools → Application → Local Storage → `coffee-office-furniture-v1` 每次操作后 ~300ms 更新。
7. 非编辑模式点咖啡机/ATM 仍开沉浸面板（`handleMachineActivate` 未编辑模式分支未动）。
