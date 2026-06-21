---
doc_type: issue-fix
status: fixed
slug: manager-thinking-too-long
date: 2026-06-21
---

# 店长正在思考过久修复记录

## 根因

`app/static/index.html` 发送消息后会一直显示“店长正在思考…”，直到 `POST /chat` 返回。后端 `/chat` 原来会无条件先调用 LLM 做意图分类，之后推荐/复盘还可能继续同步调用 LLM；`app/llm/client.py` 使用固定 60 秒 httpx timeout 且 429/网络错误会 sleep 后重试，导致外部 provider 慢时用户同步请求被长时间拖住。

## 修复

- `app/config.py` 增加 LLM 分层 timeout：connect / intent / generation / review。
- `app/llm/client.py` 改为按用途传入 timeout，移除同步链路里的等待重试，并增加 wall-clock 硬超时。
- `app/main.py` 在 `/chat` 中增加本地确定性快路径：精确商品名、价格下单、短确认、菜单/推荐词可跳过意图分类 LLM。
- `app/services/agent_orchestrator.py` 复用 `/chat` 已读取的 history，并支持把复盘/经验继承移出同步回复路径。
- `app/static/index.html` 为 `/chat` 请求增加 6 秒中途提示和 20 秒 AbortController 兜底，避免页面永久停在思考态。

## 验证

- `python -m py_compile app\main.py app\llm\client.py app\services\agent_orchestrator.py app\services\agents\reviewer_agent.py` 通过。
- `python -m pytest -q tests/test_llm_configuration.py tests/test_chat_fast_path.py tests/test_chat_confirm.py tests/test_chat_order_view.py tests/test_chat_history_fallback.py` 通过，28 passed。
- 真实 8000 端口：
  - `GET /status` 返回 `llm_timeouts.connect=3.0`、`intent=4.0`、`generation=12.0`、`review=6.0`。
  - `POST /chat`，消息“我要一杯美式咖啡”，返回确认下单文案，耗时约 4.3s。
  - `POST /chat`，消息“店长，我想喝清甜水果味但不要牛奶，推荐一下”，返回推荐文案，耗时约 16.2s，低于前端 20s 兜底。
  - Playwright 打开 `/static/index.html`，确认 `send()` 存在，20s 超时文案和 6s 中途提示文案已加载。

## 未纳入本次修复

- 全量 `python -m pytest -q` 中 `tests/test_web_presence_snapshot.py` 的 2 个用例在 `passlib/bcrypt` 后端自检时报 `password cannot be longer than 72 bytes`，发生于账号注册 hash 阶段，和本次 `/chat`/LLM 性能链路无关。
