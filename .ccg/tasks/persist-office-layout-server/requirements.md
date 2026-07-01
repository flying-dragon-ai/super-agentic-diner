# 需求：3D 编辑器布局服务端持久化

## 目标
3D 咖啡厅编辑器布局从浏览器 localStorage 迁移到服务端 MySQL 持久化，实现：
- **项目重启**（后端 uvicorn 重启）布局保留
- **跨设备/跨浏览器共享**（不再绑定单个浏览器的 localStorage）
- **全局单例布局**（管理员编辑一次，所有访客看到相同布局）

## 动机
当前 localStorage 是浏览器本地存储，在 dev 端口漂移（5174→5175 不同 origin）、换浏览器、清缓存、部署换 origin 等场景下布局丢失。用户需"项目级"持久化。推翻 `docs/features/3d-editor-completeness-alignment.md:76`「不移植后端远程同步」的既定决策（单咖啡厅已有服务端持久化需求）。

## 范围
- **后端（新增）**：
  - DB 表：布局 JSON 存储（单例，全局共享）
  - API：`GET /api/office/layout`（读）、`PUT /api/office/layout`（写）
  - service：`office_layout_service.py`
- **前端（改造）**：
  - persistence 层：异步调服务端 API
  - OfficeScene：furniture state 异步加载 + autosave 异步 PUT
  - localStorage 去留（待决策）

## 约束
- 匿名点单无门槛原则：GET 布局必须匿名可读（访客进场景要看布局）
- MySQL 唯一支持 RDBMS（SQLAlchemy + get_db 依赖注入）
- autosave 异步 PUT 不阻塞编辑 UI（失败 swallow）
- 服务端不可达时优雅降级（不白屏）

## 验收标准
1. 编辑布局 → 重启后端 → 刷新 → 布局保留
2. 浏览器 A 编辑 → 浏览器 B 打开 → 看到相同布局（全局共享）
3. 清浏览器缓存 → 布局从服务端恢复
4. 服务端不可达 → 优雅降级（默认/localStorage fallback，不白屏）

## 待决策点（4 项，需用户拍板）
1. **PUT 鉴权**：项目"无登录门槛" vs 布局编辑是管理功能
2. **localStorage 去留**：完全替换 vs 作缓存 fallback
3. **单例 vs 多布局**：全局单例（推荐，符合"全局共享"）
4. **数据迁移**：现有 localStorage 数据如何迁到服务端

## 评分：9/10（≥7，可进入构思）
- 目标明确性 3/3、预期结果 3/3、边界范围 1.5/2（4 待决策点未定）、约束 1.5/2
