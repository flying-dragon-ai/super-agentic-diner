# Smart Search 像素餐厅仓库归档

本文保存当时通过 `$smart-search-cli` 为 Coffee AI Boss 像素餐厅方向检索并抓取过的 GitHub 仓库。原始 evidence 已从临时目录复制到项目内，避免后续依赖 `C:\tmp`。

## 本地归档位置

```txt
docs/smart-search-evidence/20260619-coffee-pixel-style/
```

已归档文件：

```txt
minibistro.md
restaurant-game-canvas-js.md
restaurant-game-engine.md
restaurant-general-functions.md
restaurant-global-variables.md
restaurant-license.md
workadventure.md
```

## 当时搜索/抓取到的仓库

| 仓库 | URL | 本地 evidence | 状态 | 对 Coffee AI Boss 的用途 |
| --- | --- | --- | --- | --- |
| Restaurant-Game-Canvas-JS | https://github.com/enesbabekoglu/Restaurant-Game-Canvas-JS | `restaurant-game-canvas-js.md` | 可用 | 最重要参考。Canvas 餐厅经营游戏，适合参考场地对象数组、Canvas 绘制顺序、订单确认/拒绝、制作、配送和评分反馈。 |
| WorkAdventure | https://github.com/workadventure/workadventure | `workadventure.md` | 可用 | 多人虚拟空间参考。适合借鉴多人加入、角色在场、位置同步、状态气泡和地图热点，不建议把产品做成虚拟办公室。 |
| MiniBistro | https://github.com/MajestyHenius/MiniBistro | `minibistro.md` | 当时抓取为 GitHub 404 | 只能先作为候选方向记录。不能把它当成已验证可用代码源；后续如果要借鉴，需要重新确认仓库是否可访问、许可证和代码质量。 |

## Restaurant-Game-Canvas-JS 已抓取代码入口

这几个文件是当时通过 smart-search 保存下来的重点代码证据：

| 原文件 | 原始 URL | 本地 evidence | 可借鉴点 |
| --- | --- | --- | --- |
| README / 仓库页 | https://github.com/enesbabekoglu/Restaurant-Game-Canvas-JS | `restaurant-game-canvas-js.md` | 项目结构、玩法说明、截图、MIT 许可证说明。 |
| `game-engine.js` | https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/game-engine.js | `restaurant-game-engine.md` | 订单生命周期、购买/制作/配送流程、游戏主循环、业务动作函数。 |
| `general-functions.js` | https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/general-functions.js | `restaurant-general-functions.md` | Canvas 绘制函数、图片加载、角色移动、家具绘制、通用 UI 更新。 |
| `global-veriables.js` | https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/global-veriables.js | `restaurant-global-variables.md` | 全局状态、顾客列表、订单数组、家具/设备对象数组、设备状态字段。 |
| `LICENSE.txt` | https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/LICENSE.txt | `restaurant-license.md` | MIT License。若后续直接复制或改写实质代码，需要保留许可证声明。 |

## 可复现抓取命令

这些命令是当前归档的可复现形式，用于以后重新拉取 evidence：

```powershell
smart-search fetch "https://github.com/enesbabekoglu/Restaurant-Game-Canvas-JS" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\restaurant-game-canvas-js.md
smart-search fetch "https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/game-engine.js" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\restaurant-game-engine.md
smart-search fetch "https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/general-functions.js" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\restaurant-general-functions.md
smart-search fetch "https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/global-veriables.js" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\restaurant-global-variables.md
smart-search fetch "https://raw.githubusercontent.com/enesbabekoglu/Restaurant-Game-Canvas-JS/main/LICENSE.txt" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\restaurant-license.md
smart-search fetch "https://github.com/workadventure/workadventure" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\workadventure.md
smart-search fetch "https://github.com/MajestyHenius/MiniBistro" --format markdown --output C:\tmp\smart-search-evidence\20260619-coffee-pixel-style\minibistro.md
```

## 取舍结论

1. 当前前端像素餐厅如果要“尽量复刻上面开源仓库的代码”，首选参考 `Restaurant-Game-Canvas-JS`，尤其是对象数组、绘制分层、订单生命周期和设备状态。
2. 多人加入餐厅不要从餐厅游戏里找完整答案，应参考 `WorkAdventure` 的多人在线思路：稳定角色 ID、位置同步、状态气泡、地图热点。
3. `MiniBistro` 当时 evidence 是 404，不能作为直接代码来源，只能保留为“AI 餐厅经营/角色记忆”方向候选。
4. 直接复制 `Restaurant-Game-Canvas-JS` 的实质代码时，需要在项目内保留 MIT License 归属；更推荐提取结构和状态机思想，用 Coffee AI Boss 自己的事件模型重写。
