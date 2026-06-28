# 1Panel 面板部署指南

> 目标场景：服务器已装 **1Panel**，并已通过 1Panel 应用商店（或宿主机）提供 **MySQL 8 + Redis 7**。
> 部署架构：**app 跑 Docker 容器**（1Panel 原生管理）+ **1Panel「网站」做反向代理 + Let's Encrypt SSL**。
> 前端产物已在 `app/static/3d/`（随仓库走），**镜像免装 Node**。

---

## 架构图

```
                    互联网 (HTTPS 443)
                         │
                         ▼
              ┌──────────────────────┐
              │  1Panel 网站 (OpenResty) │  ← your-domain.com
              │  反向代理 + SSL + WSS    │
              └──────────┬───────────┘
                         │ proxy_pass http://127.0.0.1:8000
                         │ (含 /ws WebSocket upgrade)
                         ▼
              ┌──────────────────────┐
              │  crossroads-agent-cafe 容器   │  127.0.0.1:8000
              │  (uvicorn, 单 worker) │
              └───────┬────────┬─────┘
                      │        │
          MySQL ──────┘        └───── Redis
       （1Panel 应用商店 / 宿主机，通过 host.docker.local 连）
```

---

## Step 0. 前置确认（在 1Panel 终端跑）

```bash
# 1) 1Panel 已装 + Docker 正常
docker version && echo "Docker OK"

# 2) 确认 MySQL / Redis 的部署形态
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | grep -iE 'mysql|redis|mariadb'
```

- **若列出 mysql/redis 容器**（1Panel 应用商店装的典型情况）→ 它们已把端口映射到宿主机，app 容器用 `host.docker.local` 即可连。**继续本指南**。
- **若无输出**（mysql/redis 裸装在宿主机）→ 需确认它们 `bind-address = 0.0.0.0`（不是 127.0.0.1），否则 docker 容器连不上。检查：
  ```bash
  sudo ss -tlnp | grep -E '3306|6379'   # 看 LISTEN 地址是不是 0.0.0.0 或 *
  ```
  若是 `127.0.0.1:3306`，编辑 mysql `mysqld.cnf` 改 `bind-address = 0.0.0.0` 后重启。

---

## Step 1. 准备数据库（1Panel「数据库」面板）

1Panel 左侧 → **数据库** → **MySQL**：

1. **创建数据库**：库名 `coffee_ai`，字符集 `utf8mb4 / utf8mb4_unicode_ci`（与 `docker-compose.yml` 一致）。
2. **创建用户**：用户名 `coffee`，密码自定（**记下，待会写进 `.env`），权限 = `coffee_ai` 库的全部权限，**主机**填 `%`（允许任何来源，含 docker 网段）。
   > 1Panel 创建数据库时若勾选「创建同名用户并授权」，一步即可完成。
3. **Redis**：1Panel 应用商店装的 Redis 默认无密码即可连；若设了密码，待会写进 `.env` 的 `REDIS_PASSWORD`。

> 你本地开发已连的就是这台 MySQL（`<mysql-redis-host>`），库/用户大概率已存在；此步仅核对 `coffee` 用户允许从 docker 网段（`172.17.0.0/16` 或 `%`）连接。

---

## Step 2. 上传代码到服务器

**方式 A（推荐，SSH + git）**：在 1Panel「主机」→「终端」执行：
```bash
sudo mkdir -p /opt/crossroads-agent-cafe && sudo chown $USER:$USER /opt/crossroads-agent-cafe
git clone <你的仓库地址> /opt/crossroads-agent-cafe
cd /opt/crossroads-agent-cafe
```

**方式 B（1Panel 文件管理）**：1Panel「主机」→「文件」→ 进 `/opt/`，上传打包好的代码压缩包并解压到 `/opt/crossroads-agent-cafe/`。

---

## Step 3. 配置 `.env`（关键：改 HOST）

```bash
cd /opt/crossroads-agent-cafe
cp .env.example .env
vi .env
```

**容器部署必须改这两行**（容器内不能写 `127.0.0.1` 或公网 IP 回环，用 docker 网关名）：
```ini
MYSQL_HOST=host.docker.local
REDIS_HOST=host.docker.local
```
其余按实际填：`MYSQL_PASSWORD`（Step 1 设的）、`REDIS_PASSWORD`（若有）、`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`、`EVOMAP_NODE_ID`/`EVOMAP_NODE_SECRET`/`EVOMAP_SERVICE_LISTING_ID`、`AUTH_SECRET_KEY`（改成一串随机字符）。

> `host.docker.local` 由 compose 的 `extra_hosts: host.docker.local:host-gateway` 映射到宿主机，容器经此访问宿主机的 MySQL/Redis 端口。

---

## Step 4. 启动 app 容器

在 `/opt/crossroads-agent-cafe` 执行（1Panel 终端）：
```bash
docker compose -f deploy/docker-compose.1panel.yml up -d --build
```

首次会 build 镜像（~1–2 分钟，装 Python 依赖）。完成后：
```bash
docker compose -f deploy/docker-compose.1panel.yml logs -f   # 看启动日志
docker ps | grep crossroads-agent-cafe                                # 确认运行
curl -I http://127.0.0.1:8000/                                  # 本地验证（应返回 200 + 3D 页面）
```

容器随后会出现在 **1Panel「容器」→ 容器列表**，可直接在面板查看日志、重启、停止。

> compose 的 `command` 已在 uvicorn 启动前自动跑 `init_db.py` + `migrate_order_sources.py`（幂等），**无需手动建表迁移**。

---

## Step 5. 1Panel「网站」反向代理

1Panel 左侧 → **网站** → **创建网站** → 选 **反向代理**：

| 字段 | 填写 |
|---|---|
| 主域名 | `coffee.your-domain.com`（或你的域名） |
| 代号（备注） | crossroads-agent-cafe |
| 代理地址 | `http://127.0.0.1:8000` |
| 代理名称 | crossroads-agent-cafe |
| HTTP→HTTPS | 勾选（Step 7 配 SSL 后自动跳转） |

创建后，1Panel 生成 OpenResty 配置，**HTTP 已可访问** `http://coffee.your-domain.com`。但 **WebSocket 还不通**（下一步）。

---

## Step 6. 配置 WebSocket（关键，否则 3D 场景实时事件/在线人偶失效）

1. 1Panel **网站** → 点击刚建的网站 → **反向代理**（或「配置文件」/「Nginx 配置」，视 1Panel 版本）。
2. 找到 `location /` 块，编辑为以下内容（关键是 `Upgrade` / `Connection` / `proxy_read_timeout`）：

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;

    # —— WebSocket 必需（/ws/visualization 实时事件流 + 在线顾客 presence）——
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # 长连接保活，避免 WS 被中间层掐断
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;

    # 大模型响应 / 流式可能较慢
    proxy_buffering off;
}

# 较大的 3D 模型/贴图/音频（pp*.glb、m1.mp3 等）
client_max_body_size 64m;
```

3. 保存 → 1Panel 自动 reload OpenResty。

> 若 1Panel 版本的 UI 不暴露 nginx 配置编辑，可在服务器 `/opt/1panel/apps/openresty/openresty/conf/conf.d/<域名>.conf` 直接改后 `docker exec 1Panel-openresty-xxx openresty -s reload`。

---

## Step 7. SSL 证书（Let's Encrypt，免费自动续期）

1Panel **网站** → 进入该网站 → **HTTPS**：

1. 勾选 **启用 HTTPS**。
2. 证书来源选 **申请 Let's Encrypt 证书**（1Panel 内置 acme.sh）。
3. 填邮箱，验证方式选 **HTTP 验证**（域名已解析到本服务器即可），申请。
4. 申请成功后，开启 **强制 HTTPS**（HTTP 301 跳 HTTPS）。
5. 证书到期前 1Panel 自动续期（依赖 1Panel 计划任务，默认已配）。

> 申请前务必：① 域名 A 记录已解析到服务器公网 IP；② 1Panel 防火墙 / 云厂商安全组放行 **80 + 443**。

---

## Step 8. 验证（端到端）

```bash
# 1) HTTPS 首页（应 200）
curl -I https://coffee.your-domain.com/

# 2) 聊天 API 可达
curl -X POST https://coffee.your-domain.com/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"smoke_test","message":"你好"}'
```

浏览器开 `https://coffee.your-domain.com/`，确认：
- ✅ 3D 咖啡厅场景加载（人物、家具、贴图）
- ✅ 背景音乐播放（首次点击后触发）
- ✅ 可匿名聊天点单（`/chat` 不需登录）
- ✅ 右上角在线人偶 / 服务员走动（WebSocket 通的标志——若不动，回 Step 6 查 upgrade 头）

---

## 日常运维

| 操作 | 命令 / 入口 |
|---|---|
| 查日志 | 1Panel「容器」→ crossroads-agent-cafe → 日志；或 `docker logs -f crossroads-agent-cafe` |
| 重启 | 1Panel「容器」→ 重启；或 `docker restart crossroads-agent-cafe` |
| 改了 `.env` | `cd /opt/crossroads-agent-cafe && docker compose -f deploy/docker-compose.1panel.yml up -d`（重建容器加载新 env） |
| 拉新代码 + 重启 | `cd /opt/crossroads-agent-cafe && git pull && docker compose -f deploy/docker-compose.1panel.yml up -d --build` |
| **前端更新**（改了前端） | 本地 `cd frontend && npm run build` → 提交 `app/static/3d/` → push → 服务器 `git pull && docker compose ... up -d --build` |
| 查看数据库 | 1Panel「数据库」→ coffee_ai → 在线管理 / phpMyAdmin |
| 停止 / 卸载 | `docker compose -f deploy/docker-compose.1panel.yml down`（数据在 MySQL，不丢） |

---

## 故障排查

| 现象 | 原因 / 解决 |
|---|---|
| 容器启动报 `Can't connect to MySQL` | `.env` 的 `MYSQL_HOST` 没改 `host.docker.local`；或 mysql `bind-address=127.0.0.1`（改 0.0.0.0）；或 `coffee` 用户主机限制（改 `%`） |
| 容器启动报 `Access denied for user 'coffee'` | Step 1 的用户密码与 `.env MYSQL_PASSWORD` 不一致；或用户没授权 `coffee_ai` 库 |
| `curl 127.0.0.1:8000` 通但浏览器开域名 502 | 1Panel 反代代理地址写错（应为 `http://127.0.0.1:8000`）；或容器挂了（看日志） |
| 页面打开但人偶/事件不刷新、背景音乐无 | nginx 缺 WebSocket upgrade 头（Step 6）；或浏览器拦混合内容（域名 HTTPS 但资源 HTTP） |
| 申请 SSL 失败 | 域名没解析到本机 / 80 端口被防火墙拦 / 80 被占用 |
| 3D 模型/音乐加载 404 | `client_max_body_size` 太小，或 nginx 配置未覆盖 `/3d/` 静态路径（一般 proxy_pass 全转发即可） |
| 想用多 worker 提吞吐 | 当前 `--workers 1`。多 worker 会割裂 `/ws/visualization` 在线 presence；需先引 Redis pub/sub 同步再改 |

---

## 附录：不用 Docker 的替代路径（systemd 裸机）

若不想用容器，仍可用 `scripts/start.sh` + `deploy/crossroads-agent-cafe.service`（见同目录 `deploy.md`）。1Panel 反代 + SSL 步骤（Step 5/6/7）完全通用，只需把代理地址指向 `http://127.0.0.1:8000`（裸机 uvicorn 监听同样端口）。
