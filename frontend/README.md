# Crossroads Agent Café - Frontend (Phaser 3 + Colyseus)

阶段 0 脚手架：基于 Vite + TypeScript 的 Phaser 3 游戏客户端，预留 Colyseus 客户端接入点。

## 环境变量

复制 `.env.example` 为 `.env`，按需修改 Colyseus 服务地址：

```
cp .env.example .env
```

```
VITE_COLYSEUS_URL=ws://localhost:2567
```

## 开发

```
npm install
npm run dev
```

默认开发服务地址：`http://localhost:5173`。
Boot 场景会在控制台打印 `[Boot] Phaser ready` 与 `[Boot] connected? (TODO)`，并在画面居中显示 `Crossroads Agent Café - Phaser Boot OK`。

## 构建

```
npm run build
```

执行 `tsc && vite build`，构建产物输出到 **`../app/static/game`**（即 `app/static/game/`），不会触碰 `app/static/` 根目录下的现有静态资源。

## 预览构建产物

```
npm run preview
```

## 目录结构

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── .env.example
├── .gitignore
└── src/
    ├── main.ts                      # Phaser.Game 启动入口 + BootScene
    └── network/
        └── colyseusClient.ts        # Colyseus Client 单例 + joinCoffeeRoom()
```

## 产物路径

- 源码：`frontend/src/`
- 构建产物：`app/static/game/`（供 FastAPI 静态托管）
