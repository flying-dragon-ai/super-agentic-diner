# 部署指南（Linux）

> 目标场景：一台 Linux 服务器，**已自建 MySQL 8 + Redis 7**，把后端 + 前端代码部署上去。
> 前端构建产物已随仓库提交到 `app/static/3d/`，**服务器免装 Node**。

---

## 0. 前置条件

| 项 | 要求 |
|---|---|
| OS | Linux（Ubuntu 20.04+ / Debian 11+ / CentOS 8+ 等） |
| Python | 3.10+（`python3 --version` 确认） |
| MySQL | 8.0，字符集 `utf8mb4`（已自建则跳过） |
| Redis | 7.x（已自建则跳过） |
| 端口 | 默认 8000；防火墙放行或前置 nginx 反代 |
| 依赖 | `sudo` 权限（仅注册 systemd service 时需要） |

> 服务器若需要新装 MySQL/Redis，可用本仓库的 `docker-compose.yml`（`docker compose up -d`），但你的场景是**已有**，部署 app 时无需启动它。

---

## 1. 获取代码

```bash
sudo mkdir -p /opt/crossroads-agent-cafe
sudo chown "$USER":"$USER" /opt/crossroads-agent-cafe
git clone <你的仓库地址> /opt/crossroads-agent-cafe
cd /opt/crossroads-agent-cafe
```

> 从 Windows 推送时，`scripts/start.sh` 与 `.service` 的行结束符已由 `.gitattributes` 强制为 LF。若仍怀疑是 CRLF，执行：
> `sed -i 's/\r$//' scripts/start.sh deploy/crossroads-agent-cafe.service`

---

## 2. 配置环境变量

```bash
cp .env.example .env
vim .env   # 填入实际值
```

**生产模式必填 / 必须显式确认**：

```ini
ENVIRONMENT=production
DB_MODE=mysql
USE_FAKEREDIS=false
AUTH_COOKIE_SECURE=true
REGISTRATION_BONUS_CNY=0
```

- `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` —— 指向你的 MySQL。
- `REDIS_HOST/PORT`（以及启用密码时的 `REDIS_PASSWORD`）—— 指向你的 Redis。
- `REGISTRATION_BONUS_CNY=0` —— 生产默认不发注册赠金；不要通过 `ALLOW_REGISTRATION_BONUS_IN_PRODUCTION` 绕过，除非已经有明确、单独审核的业务决策。

**业务必填**：
- `LLM_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL` —— OpenAI 兼容 LLM
- `EVOMAP_NODE_ID` + `EVOMAP_NODE_SECRET` + `EVOMAP_SERVICE_LISTING_ID` —— A2A 积分支付
- `AUTH_SECRET_KEY` —— 改成至少 32 个字符的随机长字符串（生产弱密钥会拒绝启动）。
- `CORS_ALLOWED_ORIGINS` —— 同源部署可留空；如前后端跨域，只填写明确的 HTTPS origin，生产不能使用 `*`。

**校验连通性**（可选，启动脚本也会做）：
```bash
mysql -h "$MYSQL_HOST" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SELECT 1"
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING
```

---

## 3. 安装与初始化（一键脚本）

```bash
bash scripts/start.sh
```

脚本自动完成 5 步：
1. 检测/创建 `.venv`
2. 加载 `.env` 并显示实际 `DB_MODE` / `USE_FAKEREDIS`
3. `pip install -r requirements.txt`
4. 按实际配置测试 MySQL/Redis；SQLite/fakeredis 模式不探测外部服务
5. 运行规范、幂等的 `scripts/migrate_order_sources.py`

最后前台启动 uvicorn（`0.0.0.0:8000`，单 worker）。**Ctrl+C 停止**。

启动链路不会隐式灌入 demo 数据，也不会创建固定管理员。`scripts/init_db.py` 默认同样是 schema-only；`--seed-demo` 仅允许本地演示环境显式使用。

> 首次验证可先用脚本前台跑。`curl http://localhost:8000/health/live` 应返回 `200`；`curl http://localhost:8000/health/ready` 只有在数据库、Redis/fakeredis 与 3D 发布资源都可用时才返回 `200`，否则返回 `503`。确认 readiness 后再改用 systemd 托管（下一步）。

---

## 4. systemd 托管（推荐：开机自启 + 崩溃重启）

```bash
# 创建专用用户（可选；若用已有用户，修改 .service 里的 User/Group）
sudo useradd -r -s /sbin/nologin coffee || true
sudo chown -R coffee:coffee /opt/crossroads-agent-cafe

# 注册 service
sudo cp deploy/crossroads-agent-cafe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crossroads-agent-cafe

# 查看状态与日志
sudo systemctl status crossroads-agent-cafe
sudo journalctl -u crossroads-agent-cafe -f

# 探针：live 只看进程；ready 才表示可以接流量
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

若 `User=coffee` 与你的实际用户不符，编辑 `/etc/systemd/system/crossroads-agent-cafe.service` 改 `User/Group/WorkingDirectory/EnvironmentFile` 路径后 `daemon-reload`。

service 的 `ExecStartPre` 会在每次启动前运行唯一的规范迁移 `scripts/migrate_order_sources.py`；迁移失败时服务不会开始接流量。

首次需要管理员时，单独执行一次安全 bootstrap（交互输入密码；不会附带 demo 充值或注册赠金）：

```bash
cd /opt/crossroads-agent-cafe
sudo -u coffee .venv/bin/python scripts/bootstrap_admin.py --username cafe-admin
```

已有普通账号只有在显式增加 `--promote-existing` 时才会被提升为管理员。

**改 `.env` 或拉新代码后**：`sudo systemctl restart crossroads-agent-cafe`

---

## 5. nginx 反代 + HTTPS（可选，生产建议）

WebSocket（`/ws/visualization`）必须配置 upgrade 头，否则 3D 场景实时事件与在线 presence 失效：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 静态资源（3D 模型/贴图/音频较大，nginx 直出更高效）
    location /3d/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;   # 长连接
    }

    # 其余（/chat /skill /auth /agents 等）
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

HTTPS：`sudo certbot --nginx -d your-domain.com`（Certbot 自动改 nginx 配置并续期）。

---

## 6. 前端更新流程

前端源码在 `frontend/`，**产物在 `app/static/3d/`**（由 Vite `outDir: ../app/static/3d` 生成，已提交仓库）。

改了前端后，在**本地开发机**（有 Node）执行：
```bash
cd frontend
npm install        # 首次或依赖变更时
npm run build      # 产物自动输出到 ../app/static/3d/
```
然后 `git add app/static/3d && git commit`，推送后在服务器：
```bash
cd /opt/crossroads-agent-cafe && git pull
sudo systemctl restart crossroads-agent-cafe
```

---

## 7. 容器化部署（可选替代方案）

若偏好 Docker：
```bash
docker build -t crossroads-agent-cafe:latest .
docker run -d --name crossroads-agent-cafe \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  crossroads-agent-cafe:latest
```

镜像启动命令会先运行唯一的规范迁移，再启动 uvicorn；无需再串行执行 `init_db.py` 和第二个迁移脚本。启动后检查：

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
docker inspect --format '{{json .State.Health}}' crossroads-agent-cafe
```

如需管理员账号，显式执行：

```bash
docker exec -it crossroads-agent-cafe python scripts/bootstrap_admin.py --username cafe-admin
```

注意：容器内不含 MySQL/Redis，需 `.env` 指向可达的 db 地址（容器网络或宿主机 `host.docker.internal`），并确保生产 `.env` 设置 `ENVIRONMENT=production`、`AUTH_COOKIE_SECURE=true`、`REGISTRATION_BONUS_CNY=0`。

---

## 8. 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| `bash scripts/start.sh: \r` 报错 | CRLF 行结束符。执行 `sed -i 's/\r$//' scripts/start.sh`（`.gitattributes` 应已预防） |
| MySQL 连接失败 | 检查 `.env` 的 `MYSQL_*`；确认 MySQL 允许该服务器 IP 连接（非仅 localhost）；字符集需 `utf8mb4` |
| `/health/live` 为 200、`/health/ready` 为 503 | 进程仍在，但数据库、Redis/fakeredis 或 `app/static/3d` 发布资源至少一项未通过；看响应中的 `checks` 和服务日志，不要让反代/负载均衡继续送流量 |
| 3D 场景开但事件/人偶不刷新 | nginx 未配 `/ws/` 的 `Upgrade/Connection` 头（见第 5 节） |
| 前端改动没生效 | 本地 `npm run build` 后是否提交了 `app/static/3d`？服务器是否 `git pull + restart`？ |
| 想要多 worker 提吞吐 | 设置 `USE_FAKEREDIS=false` 并确认 Redis 可达后，可用 `WORKERS=N bash scripts/start.sh`。`/ws/visualization` 通过 Redis Pub/Sub 同步事件，`scene.snapshot` 通过 Redis presence + 数据库事件回放恢复状态。fakeredis 是进程内模拟，不能用于多 worker。 |
| `--reload` | **生产禁用**（性能、文件监听开销、Windows 行为差异）。`start.sh` 与 systemd 均未带 |
| 权限错误 | systemd `User=coffee` 需对 `/opt/crossroads-agent-cafe` 有读写权（含 `.venv`） |
| **切分支后网页白屏/打不开** | 见下方「分支切换排查清单」 |
| **切分支后 `/status` 返回 500** | `dev_Code`/`dev_x` 分支删除了 `db_mode`/`use_fakeredis` 配置项，只支持 MySQL+Redis，但 `.env` 仍设 `DB_MODE=sqlite`。解法：① 恢复 `.env` 为 MySQL/Redis 模式并确保服务可达；② 或在本地继续用 `main` 分支（支持 SQLite+fakeredis 降级） |
| **切分支后 3D 页面 JS 404** | 各分支构建产物 hash 不同（如 `index-D0k-m-ay.js` vs `index-BwgXzfEe.js`）。`git checkout` 只恢复 `index.html` 的引用，不清理旧 hash 的 `.js` 文件，但也不自动构建新的。**解法：每次切分支后必须 `cd frontend && npm run build`**，确保 `app/static/3d/assets/` 下有该分支 `index.html` 引用的 JS 文件 |
| **切分支后 `ModuleNotFoundError: passlib`** | `dev_Code` 的 `requirements.txt` 有 `passlib[bcrypt]`，而 `main` 删除了它改用裸 `bcrypt`。解法：切分支后执行 `pip install -r requirements.txt` 重新安装依赖 |

---

## 10. 分支切换排查清单

从其他分支（`dev_x`/`dev_Code`）拉取代码后无法打开网页，按以下顺序排查：

### ① 构建产物不匹配（最常见）

```bash
# 检查 index.html 引用的 JS 是否存在
grep -oP 'src="([^"]+)"' app/static/3d/index.html
# 检查该文件是否存在
ls app/static/3d/assets/

# 如果缺失，重新构建
cd frontend
npm install
npm run build
cd ..
```

**原因**：Vite 每次构建生成带 content hash 的 JS 文件名（`index-XXXX.js`）。`git checkout` 切分支时，`index.html` 被切换为新分支版本引用另一个 hash，但对应的 JS 文件可能不在当前文件系统中。

### ② 数据库配置冲突

| 分支 | 数据库模式 | Redis 模式 |
|------|-----------|------------|
| `main` | SQLite（`DB_MODE=sqlite`）或 MySQL | fakeredis（`USE_FAKEREDIS=true`）或 Redis |
| `dev_x` | SQLite（同 main） | fakeredis（同 main） |
| `dev_Code` | **仅 MySQL**（无 `db_mode` 字段） | **仅 Redis**（无 `use_fakeredis` 字段） |

```bash
# 检查当前配置
curl http://localhost:8000/status
# 预期输出: {"database":"sqlite","memory":"fakeredis",...}

# 如果切到 dev_Code 分支后启动报错，检查 .env
# dev_Code 不认 DB_MODE/USE_FAKEREDIS，强制 MySQL+Redis
# 解法：确保 MySQL 和 Redis 服务可用，或切回 main
```

### ③ Python 依赖不一致

```bash
# 切分支后重新安装
pip install -r requirements.txt

# 主要差异：
# main:          redis>=5.0.0,<6.0.0 + fakeredis>=2.20.0（降级模式）
# dev_Code:      redis>=5.0.0 + passlib[bcrypt]>=1.7.4（无 fakeredis）
```

### ④ 后端模块缺失

```bash
# 快速验证后端能启动
python -c "from app.main import app; print('OK')"

# 常见报错及解法：
# ModuleNotFoundError: app.services.autonomous_agent_service
#   → main 分支有此模块，dev_x/dev_Code 可能已删除
# ModuleNotFoundError: app.services.visitor_analytics_service
#   → main 分支有此模块，dev_x 不含
# ImportError: cannot import name 'Base' from 'app.db.database'
#   → main 分支 database.py 有 Base 导出，dev_Code 版本无
```

### ⑤ 完整恢复流程（从任意分支恢复到可运行状态）

```bash
# 1. 切回 main 分支
git checkout main

# 2. 重新构建前端
cd frontend && npm install && npm run build && cd ..

# 3. 重装依赖
pip install -r requirements.txt

# 4. 重启服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 5. 验证
curl http://localhost:8000/status       # 应返回 JSON
curl -I http://localhost:8000/3d        # 应返回 200
curl -I http://localhost:8000/3d/login  # 应返回 200
```

---

## 9. 目录与部署的关系

| 目录/文件 | 是否部署到服务器 | 说明 |
|---|---|---|
| `app/` | ✅ | 后端运行代码（含 `static/3d` 前端产物） |
| `scripts/` | ✅ | `start.sh` + db 初始化脚本 |
| `requirements.txt` | ✅ | Python 依赖 |
| `.env` | ✅（手动创建，不入 git） | 运行配置 |
| `frontend/` | ❌（仅开发机） | 前端源码，产物已在 `app/static/3d` |
| `docs/` `tests/` `.agents/` | ❌ | 文档/测试/对外 Skill，运行不需要 |
| `.claude/ .codestable/ .evolver/` | ❌ | AI 工具配置与项目知识库，开发期资产 |
| `docker-compose.yml` | 仅新装 db 时 | 你已有 MySQL/Redis，部署 app 不启用 |
