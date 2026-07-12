# Crossroads Agent Café

基于 **FastAPI + SQLAlchemy（SQLite/MySQL）+ fakeredis/Redis + LLM** 的轻量级 AI 点单助手 demo。
不使用向量数据库，知识检索采用「关键词 RAG」（分词 + 同义词扩展 + 否定词过滤）。

## 项目结构

```text
crossroads-agent-cafe/
├── app/                  # FastAPI 后端：对话点单 / A2A Skill / 多 Agent 协作 / 可视化事件
├── frontend/             # React 19 + Vite + R3F 3D 咖啡厅前端（构建产物 → app/static/3d）
├── tests/                # pytest 测试套件
├── scripts/              # 数据库迁移、启动（start.sh）、打包脚本
├── deploy/               # systemd service、1Panel docker-compose
├── docs/                 # 设计文档、部署指南（deployment/deploy.md / deployment/deploy-1panel.md）、归档清单
├── .agents/skills/       # 对外 A2A 超级点单 Skill
├── docker-compose.yml    # MySQL 8 + Redis 7 本地依赖
├── Dockerfile            # 后端容器镜像
├── requirements.txt      # Python 依赖
├── .env.example          # 环境变量模板（复制为 .env 并填入真实配置）
└── README.md
```

完整架构与变更记录见 [CLAUDE.md](./CLAUDE.md)。
文档目录索引见 [docs/README.md](./docs/README.md)。

## 架构对应面试题三个任务

| 任务 | 模块 | 说明 |
|------|------|------|
| 一·存储 | `app/db/models.py`、`app/memory/chat_history.py` | MySQL 三张表 + Redis List 短期记忆 |
| 二·RAG | `app/rag/keywords.py`、`app/rag/retrieval.py` | 关键词提取 + 否定词过滤 |
| 三·下单 | `app/services/order_service.py` | 事务 + 行锁安全扣款 |

## 快速开始

### 1. 启动 MySQL + Redis
```bash
docker-compose up -d
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY
```

### 4. 初始化 / 升级 Schema
```bash
python scripts/migrate_order_sources.py
```

`scripts/migrate_order_sources.py` 是 SQLite/MySQL 共用的规范迁移入口，可幂等重复运行。`scripts/init_db.py` 默认也只调用该迁移，不会创建固定账号、充值或演示订单。

仅在本地演示环境需要样例数据时显式执行：
```bash
python scripts/init_db.py --seed-demo
```

生产环境禁止启用 demo seed，并应设置 `REGISTRATION_BONUS_CNY=0`。如需管理员账号，使用一次性显式命令；密码通过交互、标准输入或受保护文件读取，不接受命令行明文密码：

```bash
python scripts/bootstrap_admin.py --username cafe-admin
```

### 5. 启动服务
```bash
uvicorn app.main:app --reload
```
打开 `http://localhost:8000/docs` 查看接口。

健康探针：

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

`/health/live` 仅检查进程存活；`/health/ready` 会检查当前数据库、Redis/fakeredis 与 3D 发布资源，任一项不可用时返回 `503`，部署流量门禁应使用 readiness。

## 接口示例

**聊天 / 推荐**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"message":"店长，我想喝点清甜水果味的，但不要加牛奶，推荐一下。"}'
```

**下单（含扣款）**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"message":"就买你刚才推荐的那杯，从我余额里扣钱吧。","request_id":"req-001"}'
```

**查看用户 / 历史**
```bash
curl http://localhost:8000/user/1
curl http://localhost:8000/history/1
```
