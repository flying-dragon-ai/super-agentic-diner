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
sudo mkdir -p /opt/coffee-ai-boss
sudo chown "$USER":"$USER" /opt/coffee-ai-boss
git clone <你的仓库地址> /opt/coffee-ai-boss
cd /opt/coffee-ai-boss
```

> 从 Windows 推送时，`scripts/start.sh` 与 `.service` 的行结束符已由 `.gitattributes` 强制为 LF。若仍怀疑是 CRLF，执行：
> `sed -i 's/\r$//' scripts/start.sh deploy/coffee-ai-boss.service`

---

## 2. 配置环境变量

```bash
cp .env.example .env
vim .env   # 填入实际值
```

**必填**（启动脚本会校验，缺失直接报错退出）：
- `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` —— 指向你的 MySQL
- `REDIS_HOST/PORT` —— 指向你的 Redis

**业务必填**：
- `LLM_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL` —— OpenAI 兼容 LLM
- `EVOMAP_NODE_ID` + `EVOMAP_NODE_SECRET` + `EVOMAP_SERVICE_LISTING_ID` —— A2A 积分支付
- `AUTH_SECRET_KEY` —— 改成一串随机长字符串（生产必改；点单不依赖，但 WS 在线 presence 与 `/auth/*` 用）

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
2. 校验 `.env` 必备键
3. `pip install -r requirements.txt`
4. 测试 MySQL/Redis 连通性
5. `init_db.py`（建表+种子）+ `migrate_order_sources.py`（订单来源迁移）

最后前台启动 uvicorn（`0.0.0.0:8000`，单 worker）。**Ctrl+C 停止**。

> 首次验证可先用脚本前台跑，确认 `curl http://localhost:8000/` 返回 3D 页面后，再改用 systemd 托管（下一步）。

---

## 4. systemd 托管（推荐：开机自启 + 崩溃重启）

```bash
# 创建专用用户（可选；若用已有用户，修改 .service 里的 User/Group）
sudo useradd -r -s /sbin/nologin coffee || true
sudo chown -R coffee:coffee /opt/coffee-ai-boss

# 注册 service
sudo cp deploy/coffee-ai-boss.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coffee-ai-boss

# 查看状态与日志
sudo systemctl status coffee-ai-boss
sudo journalctl -u coffee-ai-boss -f
```

若 `User=coffee` 与你的实际用户不符，编辑 `/etc/systemd/system/coffee-ai-boss.service` 改 `User/Group/WorkingDirectory/EnvironmentFile` 路径后 `daemon-reload`。

**改 `.env` 或拉新代码后**：`sudo systemctl restart coffee-ai-boss`

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
cd /opt/coffee-ai-boss && git pull
sudo systemctl restart coffee-ai-boss
```

---

## 7. 容器化部署（可选替代方案）

若偏好 Docker：
```bash
docker build -t coffee-ai-boss:latest .
docker run -d --name coffee-ai-boss \
  -p 8000:8000 \
  --env-file .env \
  --restart unless-stopped \
  coffee-ai-boss:latest
```
注意：容器内不含 MySQL/Redis，需 `.env` 指向可达的 db 地址（容器网络或宿主机 `host.docker.internal`）。

---

## 8. 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| `bash scripts/start.sh: \r` 报错 | CRLF 行结束符。执行 `sed -i 's/\r$//' scripts/start.sh`（`.gitattributes` 应已预防） |
| MySQL 连接失败 | 检查 `.env` 的 `MYSQL_*`；确认 MySQL 允许该服务器 IP 连接（非仅 localhost）；字符集需 `utf8mb4` |
| 3D 场景开但事件/人偶不刷新 | nginx 未配 `/ws/` 的 `Upgrade/Connection` 头（见第 5 节） |
| 前端改动没生效 | 本地 `npm run build` 后是否提交了 `app/static/3d`？服务器是否 `git pull + restart`？ |
| 想要多 worker 提吞吐 | 当前 `--workers 1`。多 worker 会割裂 `/ws/visualization` 的在线 presence 状态，需先引入 Redis pub/sub 同步，再改 `--workers N` |
| `--reload` | **生产禁用**（性能、文件监听开销、Windows 行为差异）。`start.sh` 与 systemd 均未带 |
| 权限错误 | systemd `User=coffee` 需对 `/opt/coffee-ai-boss` 有读写权（含 `.venv`） |

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
