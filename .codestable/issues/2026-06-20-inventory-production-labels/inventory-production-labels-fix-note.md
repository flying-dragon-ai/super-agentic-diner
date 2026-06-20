---
doc_type: issue-fix
issue: 2026-06-20-inventory-production-labels
path: fast-track
fix_date: 2026-06-20
tags: [frontend, 3d, inventory, production, labels]
---

# 库存与制作系统标识不明确修复记录

## 1. 问题描述

3D 咖啡厅里点击咖啡机后打开的面板只用「库存与制作」作为总标题，内容主要是库存条目，制作系统没有单独的可见分区。咖啡机模型自身的标签也使用「Hero」「Compact」「Hopper」这类内部样式名，用户无法明确判断哪一块对应库存系统、哪一块对应制作系统。

## 2. 根因

- `frontend/src/overlays/ImmersiveOverlay.tsx` 的 brewing overlay 将库存和制作合并为一个模糊标题，并缺少制作队列/工位信息。
- `frontend/src/office3d/objects/machines.tsx` 的咖啡机标签使用模型变体名，不是业务系统名。

## 3. 修复方案

- 将咖啡机 overlay 标题改为「库存系统 · 制作系统」。
- 在 overlay 内拆成两个明确分区：
  - 「库存系统」展示原料余量。
  - 「制作系统」展示咖啡出品队列和工位状态。
- 将 3D 咖啡机标签替换为业务语义：
  - 主咖啡机：「制作系统」
  - 小型终端：「库存终端」
  - 豆仓/研磨机：「原料库存」
- 给 3D 标签增加深色底牌，提高场景中可读性。
- 重新执行 Vite 构建，更新 FastAPI 实际服务的 `app/static/3d` bundle。

## 4. 改动文件清单

- `frontend/src/overlays/ImmersiveOverlay.tsx`
- `frontend/src/office3d/objects/machines.tsx`
- `app/static/3d/index.html`
- `app/static/3d/assets/index-rKiUM0vc.js`
- `app/static/3d/assets/index-D0k-m-ay.js`（构建产物替换后删除）

## 5. 验证结果

- `npm run build`：通过，包含 `tsc --noEmit` 和 `vite build`。
- `GET http://127.0.0.1:8000/3d/scene`：返回 `200`，页面引用新 bundle `index-rKiUM0vc.js`。
- 本地 bundle 搜索：`app/static/3d/assets/index-rKiUM0vc.js` 包含「库存系统」「制作系统」「库存终端」「原料库存」。
- Playwright 桌面视口 `1366x768`：
  - 打开 `http://127.0.0.1:8000/3d/scene`。
  - 切换「吧台」视角。
  - 点击咖啡机区域。
  - 结果：overlay 打开，`opened=true`，`inventoryVisible=true`，`productionVisible=true`。
- Playwright 移动视口 `390x844`：
  - 同一路径和交互。
  - 结果：overlay 打开，两个系统分区均可见，布局上下堆叠且文字未溢出。

## 6. 遗留事项

无。
