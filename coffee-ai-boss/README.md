# 智能咖啡馆 AI 店长

基于 **FastAPI + MySQL 8 + Redis 7 + LLM** 的轻量级 AI 点单助手 demo。
不使用向量数据库，知识检索采用「关键词 RAG」（分词 + 同义词扩展 + 否定词过滤）。

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

### 4. 建表 + 灌种子数据
```bash
python scripts/init_db.py
```

### 5. 启动服务
```bash
uvicorn app.main:app --reload
```
打开 `http://localhost:8000/docs` 查看接口。

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
