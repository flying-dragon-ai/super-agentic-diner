# coffee-colyseus

Coffee AI Boss 像素餐厅的 Colyseus 0.15+ 多人服务端（阶段 0/5 脚手架）。

只负责 `colyseus-server/` 目录，是 FastAPI 主服务的旁路同步通道，不读写 MySQL/Redis，
订单真源仍由主服务持有，本服务端只镜像最小同步字段。

## 目录结构

```
colyseus-server/
├── package.json          # name=coffee-colyseus, type=module
├── tsconfig.json         # strict, NodeNext, ES2022
├── .env.example          # COLYSEUS_PORT=2567
├── .gitignore
└── src/
    ├── Server.ts         # 启动入口，define('coffee_room')
    ├── schema/
    │   └── CoffeeState.ts  # Player / NPC / Order / Seat / CoffeeState
    └── rooms/
        └── CoffeeRoom.ts   # onCreate/onJoin/onLeave + move/interact/place_order
```

## 开发

```powershell
cd colyseus-server
cp .env.example .env   # 按需改端口
npm install            # 首次需要，本脚手架不预装依赖
npm run dev            # tsx watch src/Server.ts
```

生产：

```powershell
npm run build          # tsc -> dist/
npm start              # node dist/Server.js
```

## 房间与消息

- 房间名：`coffee_room`，`maxClients = 50`
- 同步根：`CoffeeState`（players / npcs / orders / seats）
- 客户端消息：
  - `move`：`{ x, y, anim? }`，服务端做有限性 + 世界边界校验
  - `interact`：`{ action: 'sit' | 'stand', seatId? }`，座位互斥占用
  - `place_order`：暂为 stub，后续接入业务桥

## 约束

- MySQL/Redis 凭据与业务逻辑不在此处引入；本服务端目前零外部依赖（除 colyseus）。
- NodeNext 下源码 `import` 必须带 `.js` 后缀（即便源是 `.ts`）。