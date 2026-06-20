[根目录](../CLAUDE.md) > **colyseus-server** (多人服务器)

# colyseus-server/ — Colyseus 像素咖啡馆房间

## 变更记录 (Changelog)

| 时间 | 动作 | 说明 |
|------|------|------|
| 2026-06-20 | 创建 | 初始化架构师首次生成 |

---

## 模块职责

Coffee AI Boss 的 **像素风多人房间**服务器（独立于 3D 前端）。基于 Colyseus 提供权威状态同步的咖啡馆房间 `coffee_room`：玩家走动、入座、NPC 咖啡师、订单状态镜像。

> **当前状态**：业务桥接（place_order / 订单同步）为 TODO stub（见 `CoffeeRoom.ts` 注释），核心多人移动与入座已实现。可视化事件目前主要走后端 `/ws/visualization`，Colyseus 是另一条并行的像素风通道。

## 入口与启动

- **入口**：`src/Server.ts`（`gameServer.define('coffee_room', CoffeeRoom)` + `listen(port)`）
- **端口**：`COLYSEUS_PORT` 环境变量（默认 **2567**）
- **运行方式**：
  - 通常由后端 `app/colyseus_bridge.py` 在 FastAPI startup 时自动拉起子进程（优先 `node dist/Server.js`，回退 `npx tsx src/Server.ts`）。
  - 独立开发：`npm run dev`（tsx watch）、`npm run build`（tsc → dist/）、`npm start`（node dist/Server.js）

## 对外接口

- **房间**：`coffee_room`（`maxClients = 50`）
- **客户端消息**：
  - `move` → `{x, y, anim?}`（带边界校验 0..1280 × 0..960，限频 50ms patch rate）
  - `interact` → `{action: 'sit'|'stand', seatId?}`（入座/起身，释放占用）
  - `place_order` → **TODO stub**（待接业务桥）
- **服务端推送**：60 FPS simulation interval + 50ms patch rate，通过 `@colyseus/schema` 增量同步

## 关键依赖与配置

- **@colyseus/core 0.15** + **@colyseus/schema 2.0** + **@colyseus/ws-transport 0.15**
- **TypeScript 5.4** + **tsx 4.7**（dev 运行时）
- **@types/node 20**
- 编译输出 `dist/`（`tsc`），`.js` 扩展的 import 路径（ESM）

## 数据模型（`src/schema/CoffeeState.ts`，Colyseus Schema）

| Schema 类 | 字段 | 说明 |
|-----------|------|------|
| `CoffeeState`（根） | `players: MapSchema<Player>`, `npcs: MapSchema<NPC>`, `orders: ArraySchema<Order>`, `seats: MapSchema<Seat>` | 房间权威状态 |
| `Player` | sessionId, name, role, x, y, anim, seatId | 在线玩家（role 约束见后端 domain_constants.py） |
| `NPC` | id, role, x, y, anim, currentTask | 服务端权威 NPC（咖啡师等），只读 |
| `Order` | orderId, item, status, customerId, baristaId, station | 订单镜像（**真源在 MySQL order 表**） |
| `Seat` | seatId, occupiedBy | 座位占用（空串=空闲） |

> 所有同步字段必须用 `@type` 装饰器，否则不会广播。

## 核心流程

- **`onCreate`**：初始化 `CoffeeState` + 注册消息 handler + 默认 NPC（`boss_barista`）+ 50ms patch + 60fps simulate。
- **`onJoin`**：创建 Player（默认位置 320,520，role/customer，name 限 20 字符）。
- **`onLeave`**：删除 Player + 释放其占用座位。
- **`simulate`**：当前为空（留给后续 NPC 任务机）。
- **move handler**：`Number.isFinite` 校验 + 世界边界裁剪，再写 `p.x/p.y/anim`。
- **interact handler**：sit 需座位空闲；stand 释放座位。

## 测试与质量

- **无测试文件**（覆盖缺口）。
- 类型检查：`npm run build` 跑 `tsc`。

## 常见问题 (FAQ)

- **Q: 和后端 `/ws/visualization` 什么关系？** A: 两条独立通道。`/ws/visualization` 是后端事件流（3D 前端用）；Colyseus 是像素多人房间（本服务器）。`bridge_event_to_colyseus` 目前是 stub（仅 debug 日志），尚未真正打通。
- **Q: 端口被占用？** A: 设 `COLYSEUS_PORT` 环境变量；后端 `colyseus_bridge.py` 会读取同名变量传给子进程。
- **Q: 为什么 import 带 `.js`？** A: ESM + tsc 编译，TS 源写 `.js` 扩展才能在编译后正确解析。

## 相关文件清单

| 文件 | 说明 |
|------|------|
| `src/Server.ts` | Colyseus Server 入口（define coffee_room + listen） |
| `src/rooms/CoffeeRoom.ts` | 房间逻辑（join/leave/move/interact/NPC/simulate） |
| `src/schema/CoffeeState.ts` | 同步 Schema（Player/NPC/Order/Seat/CoffeeState） |
| `package.json` | 依赖与脚本（dev/build/start） |
| `tsconfig.json` | TypeScript 配置 |
