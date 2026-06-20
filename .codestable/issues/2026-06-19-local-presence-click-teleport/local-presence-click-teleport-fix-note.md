---
doc_type: issue-fix
issue: 2026-06-19-local-presence-click-teleport
path: fast-track
fix_date: 2026-06-19
tags: [visualization, presence, frontend]
---

# 本地点击导致角色瞬移到鼠标位置修复记录

## 1. 问题描述

可视化页面开启本地 presence 后，用户点击画布时，本地顾客角色会直接出现在鼠标点击位置，而不是从当前位置沿布局路径移动过去。

## 2. 根因

`app/static/order-visualization.js` 中本地点击会先走 `moveLocalPresence()`，把本地角色移动排入 queue。随后后端 WebSocket 会把同一次点击回显为 `presence.customer_moved`。

`playPresenceEvent()` 原逻辑把所有 local payload 都当成需要同步的事实位置处理，执行 `customer.position = target`，导致本地 move 回显覆盖了本地动画，表现为角色瞬移到点击点。

## 3. 修复方案

在 `playPresenceEvent()` 中对本地 `presence.customer_moved` 回显直接返回。这样：

- 本地点击仍由 `moveLocalPresence()` 的 queue 驱动路径移动；
- 远端 presence move 仍按原逻辑处理；
- 本地 join / leave 语义不变；
- snapshot replay 语义不扩大。

## 4. 改动文件清单

- `app/static/order-visualization.js`：在 `playPresenceEvent()` 中跳过本地 `presence.customer_moved` 回显的位置覆盖。

## 5. 验证结果

- `node --check app/static/order-visualization.js`：通过。
- `node --check app/static/restaurant-scene-core.js`：通过。
- 浏览器真实页面验证：打开 `http://127.0.0.1:8000/`，等待本地 presence 角色 idle 后，在 canvas 上点击对应画布点 `{x:520,y:296}`。
  - 点击前角色：`{x:72,y:280,status:"idle",bubble:"我"}`。
  - 点击后立即：`{x:72,y:280,status:"walking",bubble:"移动"}`，`immediateAtTarget=false`。
  - 1.5 秒后：`{x:136,y:264,status:"walking",bubble:"移动"}`，`movedAfterDelay=true`。

结果：角色不再瞬移到鼠标点击点，而是从当前位置开始移动。

## 6. 遗留事项

无。该修复只覆盖本地 presence move 回显，不改变远端 presence、订单、Agent 或布局持久化逻辑。
