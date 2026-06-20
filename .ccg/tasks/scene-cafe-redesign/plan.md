# 场景改造计划：office → 咖啡厅 + 灯光 bug 修复

## 需求
1. **bug**: 天气系统又暗又快（`cameraLighting.tsx` 昼夜循环有暗帧 sunIntensity 0.2-0.3，300s 周期）→ 灯光**常亮**
2. **改造**: office 办公室 → 咖啡厅，桌椅/墙面道具全换
3. **增量**: 吧台加高脚椅 + 休闲区加豆袋
4. **素材**: 主线复用 17 个现有 GLB；副线爬 CC0 新素材储备

## 方案
- 复用现有 GLB（kitchenCoffeeMachine/tableRound/loungeSofa/lamp 等），重写 `DEFAULT_FURNITURE` 布局数组 + 固定灯光
- 不破坏坐标系/渲染管线/A*寻路/Agent 系统/后端事件契约

## 布局蓝图（canvas 1800×720）
| 区域 | 位置 | 家具 |
|------|------|------|
| 吧台区 | 左 x:0-500 | executive_desk(L吧台) + coffee_machine + fridge + cabinet + computer(收银) + chair×3(高脚椅) |
| 客座区 | 中 x:480-1180 | 4 组 round_table+4 chair（2×2 错落） |
| 休闲区 | 右 x:1200-1750 | couch + table_rect(茶几) + beanbag×2 + couch_v(单人椅) |
| 墙面/装饰 | 贴墙 | whiteboard(菜单板染色) + bookshelf(展示柜) + clock + lamp×3 + plant×6 + trash×3 |

## 步骤（执行模式 B：Codex 写）
1. `cameraLighting.tsx` — 固定明亮灯光，DayNightCycle → SceneLighting
2. `furnitureDefaults.ts` — 重写咖啡厅布局（删 8 工位/机房/健身房/QA/美术室）
3. `environment.tsx` — 墙体氛围微暖
4. `furniture.tsx` — FURNITURE_TINT 暖咖啡色
5. `OfficeScene.tsx` — 同步 import（老王改）
6. 验证 `npm run build`

## 副线（老王亲自）
- 爬 CC0 咖啡厅 GLB（Poly Pizza/Quaternius/Kenney）→ `public/office-assets/models/cafe-extras/` 储备
