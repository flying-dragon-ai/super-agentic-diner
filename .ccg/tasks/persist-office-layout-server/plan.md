# 实施计划：3D 编辑器布局服务端持久化

## 方案
后端单例表（namespace='default'）存布局 JSON + GET/PUT API（匿名）；
前端 localStorage 作缓存 + 服务端作权威 + 挂载时自动迁移 localStorage→服务端。

## 步骤
### 后端
1. `app/db/models.py` — 加 `OfficeLayout` 表（layout_id PK / namespace unique / layout_json Text / updated_at）
2. `app/services/office_layout_service.py`（新建）— `get_layout` / `save_layout`（upsert）
3. `app/main.py` — import service + `OfficeLayoutRequest` model + `GET/PUT /api/office/layout`（匿名）

### 前端
4. `frontend/src/net/api.ts` — 加 `putJson` + `getOfficeLayout` / `saveOfficeLayout`
5. `frontend/src/office3d/core/persistence.ts` — 保留 localStorage（缓存）+ 新增 `fetchServerLayout` / `pushServerLayout`（best-effort）
6. `frontend/src/screens/OfficeScene.tsx` — 挂载异步 GET（服务端有→用+缓存；空+本地有→迁移上传；空+本地空→默认）；autosave effect 加 debounce 服务端 PUT

### 建表 + 验证
7. 建 office_layout 表（init_db.create_all 或手动 SQL）
8. `tsc + vite build` + 后端启动检查 + Playwright 端到端验证（编辑→重启后端→保留、跨浏览器共享）

## 影响范围
- 修改: models.py / main.py / api.ts / persistence.ts / OfficeScene.tsx
- 新增: office_layout_service.py / office_layout 表
- 推翻决策: docs/features/3d-editor-completeness-alignment.md:76「不移植远程同步」
