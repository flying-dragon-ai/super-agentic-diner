# 像素餐厅参考仓库

本文记录 Crossroads Agent Café 像素餐厅可借鉴的开源仓库和产品参考。重点不是做 Gather 式虚拟办公室，而是围绕“餐厅经营状态机 + 多人同屏 + 订单制作反馈 + 顾客情绪/结算”来吸收可落地的设计。

## 核心 GitHub 参考

| 仓库 | 链接 | 可借鉴点 | 适配到 Crossroads Agent Café |
| --- | --- | --- | --- |
| Restaurant-Game-Canvas-JS | https://github.com/enesbabekoglu/Restaurant-Game-Canvas-JS | Canvas 餐厅经营游戏，包含固定背景、家具对象数组、角色移动、订单确认/拒绝、制作、配送、按速度评分等机制。 | 最适合作为当前前端可视化场地的代码风格参考：用家具对象数组管理场地，用分层绘制实现“背景 -> 家具 -> 角色 -> 前景”，用订单状态驱动角色动作。 |
| WorkAdventure | https://github.com/workadventure/workadventure | 开源多人虚拟空间，重点是多人在线、地图热点、角色同步、WebRTC/实时状态。 | 不建议照搬成虚拟办公室，但可以借鉴多人加入餐厅、角色在场、位置同步、状态气泡、地图热点和实时事件流。 |
| MiniBistro | https://github.com/MajestyHenius/MiniBistro | 餐厅经营 + LLM/Generative Agents 方向：服务员人格、顾客偏好、满意度、记忆、日报评价。 | 适合作为 AI 经营层参考：常客画像、服务员风格、经理日报、顾客评价、异常订单解释。当前需要确认仓库可访问性和许可证后再考虑直接借代码。 |

## 产品/玩法参考

| 产品 | 链接 | 可借鉴点 | 适配到 Crossroads Agent Café |
| --- | --- | --- | --- |
| Pixel Cafe | https://store.steampowered.com/app/2409360/Pixel_Cafe/ | 咖啡/食物制作、顾客耐心、多设备、多配方、收入/小费/浪费/连击结算。 | 只借鉴玩法和视觉节奏，不直接借代码。适合扩展制作进度、顾客等待反馈和经营结算面板。 |
| The Waitress / Diner Dash 类 | https://www.seeles.ai/games/simulation/the-waitress-restaurant-management-game | 顾客入座、点单、等待、上菜、吃完、收钱、清桌的标准餐厅循环。 | 可转成后端事件状态机：进店 -> 排队 -> 点单 -> 支付 -> 制作 -> 取餐/配送 -> 评价 -> 离店。 |
| Pixel Restaurant Manager | https://andersmmg.itch.io/ | 小体量像素餐厅经营原型，适合看极简交互和资产组织。 | 只作为像素资产密度、交互简化和小地图布局参考。 |

## 当前最应该借鉴的代码结构

### 1. 场地对象数组

Restaurant-Game-Canvas-JS 的核心思路是把家具和设备做成一个对象列表，而不是在画布里到处散落手写坐标。Crossroads Agent Café 前端可以继续采用类似结构：

```js
const sceneObjects = [
  { layer: "back", type: "coffee-bar", x: 30, y: 70, w: 178, h: 88, label: "BREW" },
  { layer: "back", type: "service-counter", x: 402, y: 98, w: 170, h: 82, label: "ORDER" },
  { layer: "back", type: "pickup-shelf", x: 442, y: 218, w: 102, h: 52, label: "PICKUP" },
  { layer: "back", type: "table-set", x: 118, y: 274, w: 116, h: 54, label: "TABLE" },
  { layer: "front", type: "floor-sign", x: 558, y: 274, w: 58, h: 28, label: "LIVE" },
];
```

这样后续要调整场地时，只需要改对象列表和少量绘制函数，不需要重写整段 Canvas 代码。

### 2. 分层绘制顺序

推荐绘制顺序：

```txt
背景地板/墙面
后景家具
角色/多人顾客/员工
前景家具或遮挡物
气泡和 UI 提示
```

这和 Restaurant-Game-Canvas-JS 的餐厅画法一致，能避免角色和家具遮挡关系混乱。

### 3. 订单状态机

Crossroads Agent Café 已经有后端 `VisualizationEvent` 和 WebSocket 推送。下一步应把视觉演出稳定绑定到餐厅状态，而不是只播放一段固定动画：

```txt
customer.enter
customer.queue
customer.ordering
order.confirming
payment.pending
payment.paid
barista.grinding
barista.brewing
barista.plating
waiter.pickup
waiter.deliver
customer.review
customer.leave
```

### 4. 多人同步

WorkAdventure 值得借鉴的是多人在线模型，不是虚拟办公室 UI。Crossroads Agent Café 的最小多人同步模型应包含：

```txt
customer_id / consumer_id / user_id
display_name
position { x, y }
direction
status
bubble
current_order_id / correlation_id
last_seen_at
```

前端收到 WebSocket 事件时，用稳定 ID 更新对应角色，而不是只有一个 `customer:active`。这样才能支持多人同时加入餐厅、同时等待、同时点单和独立离店。

## 推荐优先级

1. 先复刻 Restaurant-Game-Canvas-JS 的场地对象和分层绘制方式，减少手写散乱装饰。
2. 去掉不必要的路线虚线/装饰线，保留清晰的收银台、制作区、取餐区、餐桌区。
3. 用稳定顾客 ID 支持多人同时在场。
4. 让订单事件只驱动当前顾客，不影响其他顾客。
5. 再补自由移动同步：收到带坐标的顾客事件时直接更新角色位置。
6. 最后补 MiniBistro 式 AI 角色记忆、满意度、日报和顾客评价。

## 许可注意

- `Restaurant-Game-Canvas-JS` 可作为 Canvas 餐厅经营实现的主要代码参考；借代码前仍应保留原仓库许可证信息。
- `WorkAdventure` 更适合作为架构参考；如果直接复制代码，需要单独核对许可证兼容性。
- `MiniBistro` 当前先作为方向参考；直接使用前需要确认仓库可访问性、许可证和代码质量。
- `Pixel Cafe`、`The Waitress`、`Pixel Restaurant Manager` 属于产品/玩法参考，不应直接复制素材或商业代码。
