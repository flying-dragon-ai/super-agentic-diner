# Cafe Extras — 咖啡厅增强素材（CC0 储备）

本目录存放从 [Poly Pizza](https://poly.pizza) 下载的 CC0 免费 3D 模型，用于后期扩展咖啡厅场景。
当前主线场景仍使用 `../furniture/` 下 Claw3D 移植的 GLB；本目录是**储备**，未接入渲染。

## 素材清单

| 文件 | 来源模型页 | 作者 | 用途 | 状态 |
|------|-----------|------|------|------|
| ppCoffeeMachine.glb | https://poly.pizza/m/7kKSsnCcNC | J-Toastie | 咖啡机（增强版，57KB） | 📦 储备 |
| ppEspresso.glb | https://poly.pizza/m/1PH31usRIi8 | Google (Poly) | 意式咖啡，170KB | ❌ 弃用 |
| ppCoffeeCup.glb | https://poly.pizza/m/K5bW4LiHUg | Zsky | 咖啡杯，15KB | ❌ 弃用 |

## ⚠️ ppCoffeeCup / ppEspresso 弃用说明

2026-06-20 实测发现：这两个模型原始 bounding box 尺寸单位严重不统一——`ppCoffeeCup` 约 3mm、`ppEspresso` 约 104m，差 **~3.5 万倍**。任何单一 `FURNITURE_SCALE` 都无法让两者同时渲染成合理大小（接入尝试失败 5 次）。

**已改用程序化绘制**：`objects/furniture.tsx` 的 `CupProp` 组件用 `cylinderGeometry` 直接画杯子（`coffee_cup` r4cm×h9cm 白陶瓷、`espresso` r2.8cm×h6cm 小杯），尺寸 100% 可控。这两个 GLB 文件保留在目录里仅作历史归档，**不再被代码引用**（`FURNITURE_GLB` 映射已移除）。

`ppCoffeeMachine` 尺寸正常，仍作二期储备。

## License

Poly Pizza 模型多为 CC0 / CC-BY，免登录下载。使用前请到对应模型页确认具体 license 并按需署名。

## 命名规范

`pp` 前缀 = Poly Pizza 来源，与 `../furniture/` 下 Claw3D 移植的 `kitchen*`/`table*` 等区分。

## 后期启用方式

1. 在 `objects/furniture.tsx` 的 `FURNITURE_GLB` 映射里加条目，例如：
   ```ts
   coffee_machine_v2: "/3d/office-assets/models/cafe-extras/ppCoffeeMachine.glb",
   ```
2. 在 `core/furnitureDefaults.ts` 布局里使用新 type
3. 同步 `FURNITURE_SCALE` / `FURNITURE_TINT`（参考现有同类型参数微调比例和染色）
4. 若新 type 需要寻路阻塞，在 `core/geometry.ts` 的 `ITEM_FOOTPRINT` / `ITEM_METADATA` 补条目
