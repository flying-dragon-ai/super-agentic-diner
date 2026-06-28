# Pixel Agents 集成评估与 A2A 点单可视化说明

## 调研结论

`pixel-agents` 是一个 VS Code 扩展源码项目，用像素办公室把 Claude Code 多 Agent 会话可视化。它把每个 Agent 映射为一个 Canvas 中的像素角色，角色会根据 Agent 活动表现为走动、入座、打字、等待输入、等待授权等状态。

它的主要能力包括：

- React + Canvas 的像素办公室渲染。
- 角色 sprite、方向、路径移动、状态动画。
- 办公室布局、地板、墙体、家具和座位管理。
- VS Code `postMessage` 和 standalone WebSocket 两类通信方式。
- Agent 活动、等待、权限提醒、子 Agent 等状态展示。

它当前不是面向业务 Web 应用的通用 SDK，也不是咖啡点单业务引擎。直接引入会带来 VS Code 扩展、Claude Code CLI、React 19、Vite、Fastify、WebSocket 协议和 asset loader 等大量无关复杂度。

因此当前项目的 MVP 选择复用它的产品形态和技术思路：用 Canvas 做像素场景，用事件驱动角色状态和移动，不直接引入 `pixel-agents` 代码或依赖。

## 当前项目集成方式

当前项目是 FastAPI + 静态 HTML 页面，聊天发送逻辑在 `app/static/index.html` 的 `send()` 函数中。MVP 新增了三个集成点：

- `app/static/order-visualization.css`：点单可视化区域样式。
- `app/static/order-visualization.js`：本地事件总线、状态机、Canvas 渲染和动画队列。
- `app/main.py`：挂载 `/static`，让新增 CSS/JS 可被浏览器加载。

页面中的可视化区域位于右侧栏顶部，展示：

- 咖啡馆场景 Canvas。
- 当前状态标签。
- 点单流程进度条。
- 最近事件时间线。

## 事件和状态

前端通过 `window.OrderVisualization` 暴露最小 API：

- `emit(type, payload)`：触发点单可视化事件。
- `handleChatResult(data)`：根据 `/chat` 响应推进可视化状态。
- `reset()`：重置场景。
- `subscribe(handler)`：订阅内部事件，供后续调试或外部状态管理接入。

当前事件类型：

- `message:sent`
- `customer:walk_to_counter`
- `order:processing`
- `order:created`
- `coffee:making`
- `order:completed`
- `order:failed`
- `order:cancelled`

当前角色状态：

- `idle`
- `walking`
- `ordering`
- `waiting`
- `making`
- `completed`
- `failed`
- `cancelled`

MVP 状态推进规则：

- 用户消息发送后，立即触发 `message:sent`，顾客从顾客区走向点单台。
- `/chat` 返回后，触发 `order:processing`。
- 如果响应包含 `order_id`，进入等待、制作、取餐完成流程。
- 如果响应或网络请求表现为失败，进入失败状态并显示错误气泡。
- 清空对话时，调用 `reset()` 回到 `idle`。

## 与后端关系

MVP 不改变 `/chat` 请求体、响应结构、扣款事务或订单创建逻辑。动画是展示层，不能阻塞业务流程。

当前 `/chat` 只有一次性响应，所以 `waiting`、`making`、`completed` 是前端展示型状态，不代表后端真实制作进度。后续如果需要真实进度，建议新增后端事件接口：

- SSE：适合单用户页面订阅订单状态。
- WebSocket：适合多角色、多用户、多人协作场景。
- 响应字段扩展：例如 `visualization_status` 或 `order_phase`，适合最小改造。

## 本地运行与验证

启动方式沿用当前项目：

```bash
docker-compose up -d
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload
```

访问：

```text
http://localhost:8000/
```

手动验收：

- 打开页面后，右侧栏顶部出现 A2A 点单过程区域，初始状态为 `idle`。
- 发送任意文字消息后，顾客角色开始移动并进入 `walking`、`ordering`。
- 发送可确认下单的消息并产生 `order_id` 后，角色进入 `waiting`、`making`、`completed`。
- 网络错误或接口错误时，角色进入 `failed`，原聊天输入仍恢复可用。
- 用户信息、最近订单、快捷按钮、清空对话仍保持原行为。

## 后续增强路径

- 后端已新增 Agent 注册、动作上报、事件持久化和 `/ws/visualization` 实时广播。
- 可视化模块已从单顾客本地状态机升级为多角色场景，支持 `customer`、`waiter`、`cashier`、`barista`、`manager`。
- Agent 工具接入采用 `API + Skill` 形态，唯一对外入口位于 `.agents/skills/a2a-super-order/`。
- API 契约见 `docs/agent-integration-api.md`。
- 后续可继续把订单制作进度从前端演示动作替换为更细粒度的真实后端业务状态。
- 如果项目迁移到 React/Vite，再把 `order-visualization.js` 拆为 `OrderGameScene`、`useOrderVisualization` 和 `orderEventBus`。
- 如果需要完整办公室编辑器或 Agent 编排 UI，再评估抽取 `pixel-agents` 的 `webview-ui/src/office` 模块。
