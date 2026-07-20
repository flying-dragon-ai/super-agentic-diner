# Crossroads Agent Café 缺陷优化台账

更新时间：2026-07-12
基线提交：`4b444c8`

## 使用规则

本台账是全仓缺陷清零工作的唯一进度入口。每次只领取当前最高优先级且依赖已满足的问题；修复前保留复现证据，修复后附 focused test、回归命令和数据完整性证据。

状态流转固定为：

`Candidate → Confirmed → In Progress → Fixed → Verified → Closed`

- `Candidate`：静态扫描或架构审查发现，尚需针对性测试证实。
- `Confirmed`：已有源码、运行时、数据库或浏览器证据。
- `Fixed`：代码已修改，但尚未完成该问题的全部验收。
- `Verified`：focused test 已通过；合并批次验收后才能转为 `Closed`。
- `Not Reproducible`：必须附不可复现证据，不能用现有测试“碰巧通过”代替。
- 禁止在默认测试中访问开发服务、真实 MySQL/Redis、LLM 或 EvoMap。
- 禁止删除、替换或重置 `coffee_ai.db`、WAL/SHM、`.env*` 或用户现有工作区修改。
- 涉及真实数据清理时必须先备份、dry-run、核对外键闭包，再单独获得执行授权。

## 安全测试入口

默认测试会在系统临时目录创建进程专属 SQLite，强制 fakeredis、清空真实 LLM/EvoMap 凭据，并阻止真实网络 socket：

```powershell
python -m unittest discover -s tests -v
python -m pytest tests -q
```

Live HTTP 测试只能在单独进程中运行，并且拒绝正常开发端口 `8000`：

```powershell
$env:RUN_LIVE_TESTS = "1"
$env:LIVE_TEST_BASE_URL = "http://127.0.0.1:8022"
$env:LIVE_TEST_INSTANCE_ID = "token-flow-local"
python -m pytest tests/test_token_transaction_flow.py -v
```

MySQL 集成测试只能指向显式的 disposable test database；库名必须以 `_test` 结尾：

```powershell
$env:RUN_MYSQL_INTEGRATION = "1"
$env:DB_MODE = "mysql"
$env:MYSQL_DATABASE = "coffee_ai_integration_test"
python -m pytest tests/test_product_wallet_integration.py -v
```

Live HTTP 与 MySQL 集成测试不得在同一个进程中同时启用。

当前 T01 focused verification：

- `python -m unittest discover -s tests -p 'test_environment_guard.py' -v`：9 passed。
- `python -m pytest tests/test_environment_guard.py tests/test_token_transaction_flow.py tests/test_product_wallet_integration.py -q`：9 passed，12 skipped；没有执行 live/MySQL 请求。
- 临时 SQLite 上的 catalog 与 autonomous DB 测试：11 passed。
- focused DB 测试前后 `coffee_ai.db` 的 SHA-256 与修改时间均未变化。
- 最终默认安全回归：`python -m pytest -q` 为 148 passed、12 skipped；`python -m unittest discover -s tests` 为 159 passed、12 skipped。默认门禁未启用 live HTTP 或 MySQL 集成写入。

T01 授权清理结果（脱敏）：

- 执行前保留了两个清理前备份；两个备份的只读 dry-run 得到完全相同的闭合范围：30 consumers、30 users、35 agents、40 ledgers、35 orders、35 order items、35 balance transactions、895 visualization events。
- execute 使用上述精确计数作为硬门禁；执行后目标测试行全部归零。
- 两个受影响商品分别补回 10 件和 25 件，最终库存恢复为 70 和 100；补偿总量与 35 条 order items 一致。
- 备份/源库完整性门禁通过，执行后 `PRAGMA quick_check=ok`。`PRAGMA foreign_key_check` 在执行前后均为 73 条，确认全属既有问题，本次清理未新增外键违规。

## T01：止血、测试隔离与数据恢复

| ID | 严重度 | 问题与证据摘要 | 状态 | 下一验收动作 |
|---|---|---|---|---|
| T01-001 | P0 | `test_token_transaction_flow.py` 原先固定请求 `127.0.0.1:8000`，默认发现即可向已有服务注册 Consumer/Agent 并下单。现已增加三重 live 门禁、拒绝端口 8000，并在每次 `_api` 调用前二次校验。 | Verified | 在 disposable 端口运行一次显式 live 回归，再转 Closed。 |
| T01-002 | P0 | MySQL 集成测试原先在模块收集阶段调用 `pymysql.connect()`，只要配置库可达就会写入并运行迁移。现已改为默认零探测，要求 `RUN_MYSQL_INTEGRATION=1`、`DB_MODE=mysql`、显式 `_test` 库名。 | Verified | disposable MySQL 可用后运行集成套件，再转 Closed。 |
| T01-003 | P0 | 多个默认测试直接使用 `SessionLocal`、`Base.metadata.create_all()` 或 `TestClient`，可能命中 `.env` 指向的现有数据库。现已统一在 app 导入前加载 `tests/_test_env.py`，使用临时 SQLite/fakeredis 并阻断网络；全量 pytest/unittest 均通过。 | Verified | 保持默认门禁为零外部连接；只有显式 disposable 环境才启用 live/MySQL 测试。 |
| T01-004 | P0 | 先前 live 测试留下的 Consumer、Agent、订单、ledger、库存/流水影响已按单独授权流程清理；两个清理前备份和 dry-run 精确计数一致，execute 后目标范围归零。 | Verified | 保留受控备份，并在台账中仅保留脱敏计数证据；待 T01 全量安全回归通过后转 Closed。 |
| T01-005 | P1 | 外键闭包、钱包/credits 流水与库存补偿已纳入幂等清理工具；35 件库存已精确补回，quick check 通过，外键违规数执行前后相同且无新增。 | Verified | 将 73 条既有外键违规作为独立数据治理债务跟踪；T01 批次门禁通过后转 Closed。 |

## T02：发布完整性、Schema 与认证基础

当前 T02 focused verification：

- `python -m pytest -q tests/test_database_foundation.py tests/test_environment_guard.py`：20 passed。
- 更宽的 foundation/environment/Skill payment/chat/user/customer/wallet focused 集：53 passed，6 skipped。
- 规范迁移 `scripts/migrate_order_sources.py` 已在隔离 SQLite 连续运行两次；schema-only、`init_db.py` 默认不 seed、`bootstrap_admin.py` 安全输入且零赠送均有 foundation tests 覆盖。
- 隔离服务的 `/health/live` 与 `/health/ready` 正常路径均返回 200。
- 前端 build 与 TypeScript 检查通过；`python scripts/check_3d_release.py` 返回 OK。
- 最终门禁通过：`compileall`、Ruff `F821`、TypeScript `tsc --noEmit`、Vite production build、3D release integrity 与 `git diff --check` 均为成功。
- 隔离 Chromium 烟测已覆盖注册、登录、3D canvas、单一 AI 入口、ProfileModal Escape、访客消息 REST+WebSocket 去重、公共 visitor 脱敏以及普通用户 403 权限边界。
- 未完成的外部环境门禁：disposable MySQL 集成迁移、真实 Redis 竞争压测、readiness 的数据库/Redis/3D 故障注入、真实浏览器多标签/读屏/移动端回归，以及提交发布资源后在干净 checkout 执行 `check_3d_release.py --require-tracked`。以下项目因此不提前 Closed。

| ID | 严重度 | 问题与证据摘要 | 状态 | 下一验收动作 |
|---|---|---|---|---|
| T02-001 | P0 | 3D 受控构建、TypeScript 检查和本地发布引用检查已通过；校验器可检查 `index.html` 引用资源，并可要求资源已被 Git 跟踪。 | Fixed | 提交当前发布资源后，在干净 checkout 运行 `python scripts/check_3d_release.py --require-tracked`，通过后转 Verified。 |
| T02-002 | P0 | SQLite 缺列已纳入规范幂等迁移，隔离 SQLite 连跑两次并通过 foundation tests。 | Fixed | 在显式 disposable `_test` MySQL 上连跑两次迁移并核对列、索引、外键后转 Verified。 |
| T02-003 | P1 | Schema 已收敛到唯一规范入口 `scripts/migrate_order_sources.py`，使用 migration audit table、幂等重检和后置校验；启动链路不再串联两个迁移。 | Fixed | 完成 disposable MySQL 双跑与失败恢复演练后转 Verified。 |
| T02-004 | P1 | `scripts/init_db.py` 默认 schema-only；demo seed 仅允许本地显式 `--seed-demo`；固定管理员/明文密码/隐式充值已从启动链路移除，生产要求 `REGISTRATION_BONUS_CNY=0`。 | Verified | 最终全量回归和生产部署配置复审通过后转 Closed。 |
| T02-005 | P1 | 已增加无外部 I/O 的 `/health/live`，以及检查数据库、Redis/fakeredis、3D 发布资源的 `/health/ready`；正常路径均已隔离验证为 200。 | Fixed | 完成数据库、Redis 和 3D 资源分别失效时的 503 故障注入，并验证恢复后再转 Verified。 |
| T02-006 | P1 | 已增加规范 `user/admin` 角色、安全的一次性 `scripts/bootstrap_admin.py`，且新建管理员不附带 demo 余额或赠送；admin/user/guest、接口拒绝和 session 撤销已有自动化覆盖。 | Verified | 在真实部署中补做旧 Cookie、停用账号和反向代理 Cookie 属性验收后转 Closed。 |

## T03：身份、授权与外部输入安全

| ID | 严重度 | 问题与证据摘要 | 状态 | 下一验收动作 |
|---|---|---|---|---|
| T03-001 | P0 | Web 身份现由签名 Session/服务端 guest cookie 推导，客户端伪造 `user_id` 被忽略；本人/admin 资源边界、匿名 checkout 与注册后原子迁移已有回归。 | Verified | 真实浏览器补做跨账号 Cookie 与登录迁移回归后转 Closed。 |
| T03-002 | P0 | `AgentProfile.consumer_id` 已成为严格外键，Skill 下单同时校验 token、agent 与 consumer 绑定，跨 Consumer 请求被拒绝。 | Verified | disposable MySQL 上验证外键迁移及跨节点拒绝后转 Closed。 |
| T03-003 | P0 | `/skill/register` 现在要求节点所有权证明，验证失败或上游不可用时 fail closed，且验证前不创建 Consumer、Agent 或额度。 | Verified | 在受控 EvoMap 测试节点验证成功、失败和超时三条真实链路后转 Closed。 |
| T03-004 | P1 | 管理接口统一要求 admin；公共 visitor/history/topics 别名仅返回匿名化或聚合数据；布局写入要求 admin 且有版本冲突保护。 | Verified | 真实浏览器检查公共页面不再依赖管理接口后转 Closed。 |
| T03-005 | P1 | 生产弱/占位 secret、非 Secure Cookie、通配 CORS 和非零注册赠送默认被拒绝；logout 与角色提升递增 `session_version`，旧 token 失效。 | Verified | 在 HTTPS 反向代理环境验证 Secure/SameSite、登出及角色提升后的旧 Cookie 失效。 |
| T03-006 | P1 | 已增加 Redis/fakeredis 兼容限流、256 KiB ASGI 请求体上限、字段范围校验、WebSocket origin/16 KiB/频率门禁及安全响应头；413/422/429 与 chunked body 已回归。 | Fixed | 使用真实 Redis 和真实 WebSocket 客户端做并发、跨 Origin、大帧与重连验收后转 Verified。 |

## T04：订单、支付、库存与 Redis 并发一致性

| ID | 严重度 | 问题与证据摘要 | 状态 | 下一验收动作 |
|---|---|---|---|---|
| T04-001 | P0 | pending 订单使用原子 claim/migrate，迁移不覆盖目标且保留 TTL；确认请求绑定用户/agent/consumer，并通过并发单赢家测试。 | Verified | 真实 Redis 下执行高并发 claim/migrate 与进程重启回归后转 Closed。 |
| T04-002 | P0 | 免费额度改为条件更新 CAS 与唯一序号，同一最后额度只允许一个并发赢家。 | Verified | disposable MySQL 上重复执行并发测试并核对唯一约束后转 Closed。 |
| T04-003 | P0 | 付费 ledger 增加 processing/version/attempt、稳定幂等键和超时恢复；并发测试证明只有一个外部支付所有者。 | Verified | 受控 EvoMap 沙箱执行超时、重试和回调乱序演练后转 Closed。 |
| T04-004 | P0 | 库存改为原子扣减与 reservation 的 reserved/consumed/released 闭环；外部成功而本地失败进入 reconcile，幂等对账工具可恢复。 | Verified | disposable MySQL + 支付沙箱做故障注入、崩溃恢复和缺货竞争验收后转 Closed。 |
| T04-005 | P1 | guest pending 迁移已使用 Redis 原子 rename-if-absent；claim、TTL 保留和重复迁移已覆盖，关键 checkout 链路不再依赖可重入多命令窗口。 | Fixed | 在真实 Redis 对 chat list、sweep lock、online set 和 pending 全链执行竞争压测，再决定是否继续 Lua 化。 |
| T04-006 | P1 | request ID 已限制并绑定主体；钱包/库存使用条件更新，首次物化可并发收敛；多商品付费只生成一条 credits 镜像流水，对账流程幂等。 | Verified | disposable MySQL 核对 DDL 约束、执行计划及钱包/库存/ledger 对账后转 Closed。 |

## T05：3D 前端、数据保护与工程质量

| ID | 严重度 | 问题与证据摘要 | 状态 | 下一验收动作 |
|---|---|---|---|---|
| T05-001 | P1 | 3D 仅保留一个 AI 面板，接入统一 auth identity、匿名 checkout 与登录后迁移，不再保留永久隐藏的重复入口；Chromium 确认恰有一个可见 AI 入口和一个 3D canvas。 | Verified | 补做匿名准备订单→登录→确认结算的支付型浏览器旅程后转 Closed。 |
| T05-002 | P1 | visitor 消息使用稳定 `message_id`，前端按 ID upsert；Chromium 实发一条消息后 DOM 只出现一次，REST 返回与 WebSocket echo 未重复展示。 | Verified | 使用双标签和断网重连场景验证排序和历史补偿后转 Closed。 |
| T05-003 | P1 | 登录/注册统一返回 3D 应用；最终验收又发现并移除了残留的 `window.location.href = "/"`，Chromium 确认注册和重新登录后均停留 `/3d/scene`。 | Verified | 补做 Session 过期、刷新和跨标签退出回归后转 Closed。 |
| T05-004 | P1 | 布局 hydration 改为 `_uid`/规范签名去重，加入 v1→v2 迁移、版本号、2000 项上限、409 冲突与批量删除，避免近距离合法家具被静默删除。 | Fixed | 在真实浏览器导入旧布局并验证多标签冲突、不丢失和大布局性能后转 Verified。 |
| T05-005 | P1 | ProfileModal 已改为 Portal，支持焦点管理、Escape、保存状态和资料同步；Chromium 已验证 dialog 可见且 Escape 正常关闭。 | Verified | 完成焦点循环、读屏和移动端浏览器验收后转 Closed。 |
| T05-006 | P2 | BatchDeletePanel、localStorage v1→v2、静态 DOM XSS、启动/锁依赖和 CI 门禁已收口；四个 legacy 静态页不再拼接不可信 HTML，演示快速填充凭证已移除。 | Verified | 提交稳定资源 `app/static/3d/assets/app.js`，在干净 checkout 运行 CI 与 `check_3d_release.py --require-tracked` 后转 Closed。 |

## 最终本地验证快照

- `python -m pytest -q`：148 passed，12 skipped，108.42s。
- `python -m unittest discover -s tests`：159 passed，12 skipped，104.591s。
- `tests/test_security_concurrency.py`：22 passed，覆盖身份、RBAC、413/422/429、guest 原子迁移、Skill fail-closed、库存/钱包/额度/支付 CAS 与 reconcile。
- `tests/test_frontend_release_contract.py`：3 passed，锁定认证成功后必须留在 3D router、legacy 静态页不得恢复危险 HTML sink/演示密码、发布入口必须引用稳定 `app.js`。
- `python -m compileall -q app scripts tests`：通过。
- `python -m ruff check app scripts tests --select F821`：通过。
- `pnpm exec tsc --noEmit` 与 `pnpm build`：通过；Vite 构建 936 modules，稳定输出 `app/static/3d/assets/app.js`。
- `python scripts/check_3d_release.py`：`3D release integrity: OK`。
- `python scripts/check_3d_release.py --require-tracked`：当前按预期拒绝，原因是稳定产物 `app/static/3d/assets/app.js` 尚未加入 Git；提交该文件后必须在干净 checkout 复跑。
- 隔离 Chromium：注册与重新登录均到 `/3d/scene`；canvas=1、可见 AI 入口=1、legacy chat input=0、ProfileModal Escape 关闭成功、访客消息出现次数=1；公共 visitor `user_id=null`，普通用户访问管理 visitor/写布局均为 403。
- `git diff --check`：通过；仅输出 Windows 工作区 LF/CRLF 转换提示，无 whitespace error。
- 非阻断提醒：3D 主 bundle 约 1.69 MB，Vite 给出大 chunk 提示；这属于后续性能预算和代码分割优化，不影响本批正确性与安全门禁。

## 批次完成门禁

一个任务包只有同时满足以下条件才可关闭：

1. 台账中该批次不存在 `Confirmed`、`In Progress` 或未验证 `Fixed`。
2. focused tests、默认安全回归和必要的浏览器/并发/迁移验收均附结果。
3. `coffee_ai.db`、真实 MySQL/Redis、库存、钱包、订单和 ledger 的差异均已解释。
4. `git status` 中用户原有修改未被覆盖，临时测试文件不留在仓库。
5. 安全、数据库或运维复审没有未关闭的高风险项。
