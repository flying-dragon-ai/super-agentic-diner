# Coffee AI Boss — 单阶段生产镜像
#
# 前端构建产物已在 app/static/3d/（随仓库提交），镜像免装 Node、免 build。
# 若改用「部署时构建前端」策略（方案 B），在前面加一个 node 阶段：
#   FROM node:20-alpine AS fe
#   WORKDIR /fe
#   COPY frontend/package*.json ./
#   RUN npm ci
#   COPY frontend/ ./
#   RUN npm run build      # 产物输出到 ../app/static/3d
# 然后从 fe 阶段 COPY app/static/3d。
#
# 构建：docker build -t coffee-ai-boss:latest .
# 运行：docker run -d --name coffee -p 8000:8000 --env-file .env coffee-ai-boss:latest
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) 依赖（利用层缓存：requirements 不变则跳过 pip install）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) 运行所需代码（app/ 含 static/3d 构建产物；scripts/ 供容器内迁移用）
COPY app/ ./app/
COPY scripts/ ./scripts/

EXPOSE 8000

# 单 worker：/ws/visualization 在线 presence 状态在进程内，多 worker 会割裂
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
