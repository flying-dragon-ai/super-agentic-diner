"""商业咨询知识库 + 管理层AI对话服务。

用户可以与管理层（AI 驱动）进行一对一私聊，咨询商业问题：
  - Agent 经济商业模式
  - A2A 协议技术选型
  - Agent 第三空间运营策略
  - 平台合作与接入方案
  - 投资融资建议

知识库内置 Crossroads Agent Café 的业务知识，LLM 负责理解意图并给出专业回复。
对话历史存储在独立的 Redis key 命名空间（consult:），与咖啡聊天历史隔离。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.db.models import UserAccount
from app.llm import client as llm
from app.memory._redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ===== 系统知识库：平台核心信息 =====
_PLATFORM_KB = """\
# Crossroads Agent Café 平台知识库

## 定位
全球第一家基于 A2A 协议（Agent-to-Agent Protocol）的 Agent 第三空间。
Agent 在这里社交、消费、干活——不是 Demo，是真实的 B 端+C 端 Agent 生产力交易市场。

## 核心能力
1. Agent 服务市场：8 项真实 Agent 生产力服务（代码审查、技术文档、数据洞察、翻译、API集成、自动化脚本、Bug定位、测试用例生成）
2. 3D 沉浸场景：Three.js 驱动的 3D 咖啡厅，Agent 以 3D 头像在其中活动
3. A2A 协议支付：基于 EvoMap Credits 的 Agent 间支付结算（前2单免费，第3单起消耗 Credits）
4. 实时可视化：订单、交易、Agent 活动 3D 实时可视化
5. 经济价值大屏：实时展示平台 GMV、订单数、节省工时、创造价值

## 技术栈
- 后端：Python FastAPI + SQLAlchemy ORM + MySQL 8 + Redis 7
- 前端：React + TypeScript + Three.js + Vite
- AI：OpenAI 兼容协议接入 LLM，RAG 知识检索
- 协议：A2A Protocol (Apache 2.0, Linux Foundation 托管)
- 支付：EvoMap Credits 积分体系

## 商业模式
- B 端：企业接入 Agent 服务，按需付费（代码审查 ¥50/次、数据洞察 ¥120/份、API集成 ¥200/方案）
- C 端：个人用户雇佣 Agent 完成任务，按工时/产出计费
- 平台抽成：每笔交易收取服务费，维持生态运转
- 增长飞轮：更多服务 → 更多 Agent → 更多订单 → 更多收入 → 更好服务

## A2A 协议价值
- Agent 间标准化通信：跨厂商、跨平台的 Agent 互操作
- 安全可信交易：身份认证 + 支付结算 + 争议处理
- 生态开放：任何人都可以发布 Agent 服务、消费 Agent 服务

## 合作模式
- Agent 开发者：发布服务到市场，获得收入
- 企业客户：批量采购 Agent 服务，降低运营成本
- 平台共建者：贡献知识库、场景、模型，获得 Credits 奖励
- 投资人：支持 Agent 经济基础设施建设

## 常见咨询场景
1. "我想在平台上发布 Agent 服务，流程是什么？" → 注册账号 → 进入服务市场 → 创建服务卡片 → 设置定价 → 开始接单
2. "企业批量采购怎么结算？" → 联系商务团队，签订框架协议，按季度结算 + 量价优惠
3. "Agent 经济的安全性怎么保证？" → A2A 协议内置身份认证 + 加密通信 + 支付托管 + 仲裁机制
4. "平台的技术门槛高吗？" → 标准 REST API + WebSocket，任何会写 HTTP 的开发者都能接入
5. "怎么参与 A2A 协议生态？" → 参考 Linux Foundation 的 A2A 规范，实现兼容接口即可互通
"""

# ===== 管理层系统人设 =====
_SYSTEM_PROMPT = (
    "你是「Crossroads Agent Cafe」的首席战略官(CSO)，代号店长AI。\n\n"
    "你的职责：\n"
    "- 为来访用户解答关于 Agent 经济、A2A 协议、平台合作的商业问题\n"
    "- 给出专业、务实、有数据支撑的建议\n"
    "- 帮助用户理解 Agent 第三空间的商业模式和价值\n"
    "- 引导潜在合作伙伴接入平台生态\n\n"
    "回答风格：\n"
    "- 专业但亲切，像一个有经验的投资人+技术专家\n"
    "- 先理解用户真实意图，再给出针对性建议\n"
    "- 适当引用数据（订单量、节省工时、市场增速等）\n"
    "- 如果用户的问题超出你的知识范围，坦诚说明并建议联系方向\n"
    "- 回答使用中文，结构清晰，控制在 300 字以内\n\n"
    f"平台知识库：\n{_PLATFORM_KB}\n"
)

# 咨询会话在 Redis 中的 key 前缀（与 chat:history:* 隔离）
_CONSULT_PREFIX = "consult:history:"
_CONSULT_TTL = 3600  # 1 小时过期


def _consult_key(account_id: int) -> str:
    return f"{_CONSULT_PREFIX}{account_id}"


def _save_message(account_id: int, role: str, content: str) -> None:
    """将消息存入独立的 Redis List（consult:history:{account_id}）。"""
    try:
        r = get_redis_client()
        key = _consult_key(account_id)
        r.lpush(key, json.dumps({"role": role, "content": content, "ts": datetime.utcnow().isoformat()}, ensure_ascii=False))
        r.ltrim(key, 0, 29)  # 保留最近 30 条
        r.expire(key, _CONSULT_TTL)
    except RedisError:
        logger.warning("consult: Redis 写入失败 account_id=%s", account_id, exc_info=True)


def _load_history(account_id: int) -> list[dict]:
    """读取咨询历史（时间正序：最早→最新）。"""
    try:
        r = get_redis_client()
        raw = r.lrange(_consult_key(account_id), 0, -1)
    except RedisError:
        logger.warning("consult: Redis 读取失败 account_id=%s", account_id, exc_info=True)
        return []
    messages = []
    for item in reversed(raw):
        try:
            messages.append(json.loads(item))
        except (json.JSONDecodeError, TypeError):
            pass
    return messages


def consult(
    db: Session,
    account: UserAccount,
    user_message: str,
) -> dict[str, Any]:
    """管理层咨询对话。

    1. 将用户消息存入 Redis 历史记录
    2. 构造 LLM 上下文（系统提示 + 历史 + 当前消息）
    3. 调用 LLM 生成回复
    4. 将 AI 回复存入历史
    5. 返回回复内容

    降级策略：LLM 不可用时返回知识库兜底回复。
    """
    msg = (user_message or "").strip()
    if not msg:
        return {"reply": "请输入您的问题，我会为您详细解答。", "fallback": True}

    # 存入用户消息
    _save_message(account.account_id, "user", msg)

    # 构造 LLM messages
    history = _load_history(account.account_id)
    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})

    # 调用 LLM
    try:
        if not llm.has_real_key():
            reply = _fallback_reply(msg)
        else:
            reply = llm._post_chat_completion(messages, temperature=0.6, timeout_seconds=30.0)
    except Exception:
        logger.warning("consult: LLM 调用失败，使用兜底回复", exc_info=True)
        reply = _fallback_reply(msg)

    # 存入 AI 回复
    _save_message(account.account_id, "assistant", reply)

    return {
        "reply": reply,
        "fallback": reply.startswith("【系统提示】"),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def get_consult_history(account: UserAccount) -> list[dict[str, str]]:
    """获取用户的咨询对话历史。"""
    return _load_history(account.account_id)


def clear_consult_history(account: UserAccount) -> int:
    """清空用户的咨询对话历史，返回清除的条数。"""
    try:
        r = get_redis_client()
        key = _consult_key(account.account_id)
        count = r.llen(key)
        r.delete(key)
        return int(count)
    except RedisError:
        return 0


def _fallback_reply(msg: str) -> str:
    """LLM 不可用时的兜底回复：基于关键词规则匹配知识库。"""
    if any(k in msg for k in ("发布", "上架", "怎么卖", "卖服务")):
        return (
            "【系统提示】关于在平台发布 Agent 服务：\n\n"
            "1. 注册账号并登录\n"
            "2. 进入「Agent 服务市场」页面\n"
            "3. 创建服务卡片（名称、描述、定价）\n"
            "4. 服务自动上架，等待用户下单\n\n"
            "目前平台已有 8 项标准服务（代码审查 ¥50、数据洞察 ¥120 等），"
            "您也可以发布自定义服务。详细流程请联系商务团队。"
        )

    if any(k in msg for k in ("价格", "费用", "多少钱", "收费", "成本")):
        return (
            "【系统提示】平台服务定价参考：\n\n"
            "- 代码审查：50元/次\n"
            "- 技术文档：80元/份\n"
            "- 数据洞察：120元/数据集\n"
            "- 多语言翻译：30元/千字\n"
            "- API 集成方案：200元/方案\n"
            "- 自动化脚本：100元/个\n"
            "- Bug 定位：60元/次\n"
            "- 测试用例：70元/模块\n\n"
            "企业批量采购可享量价优惠，具体请联系商务。"
        )

    if any(k in msg for k in ("接入", "对接", "集成", "A2A", "协议", "API")):
        return (
            "【系统提示】平台接入方式：\n\n"
            "1. 标准 REST API + WebSocket\n"
            "2. A2A 协议兼容（Apache 2.0 开源）\n"
            "3. 前 2 单免费体验，第 3 单起消耗 EvoMap Credits\n"
            "4. 提供完整文档和代码示例\n\n"
            "技术门槛低，任何会写 HTTP 的开发者都能接入。"
        )

    if any(k in msg for k in ("合作", "投资", "融资", "商务", "BD")):
        return (
            "【系统提示】合作模式：\n\n"
            "- Agent 开发者：发布服务 → 获得收入\n"
            "- 企业客户：批量采购 → 降低成本\n"
            "- 平台共建者：贡献资源 → 获得 Credits\n"
            "- 投资人：支持 Agent 经济基建\n\n"
            "欢迎进一步沟通，请发送邮件或预约线下交流。"
        )

    return (
        "【系统提示】感谢您的咨询！我是 Crossroads Agent Café 的战略官助手。\n\n"
        "我可以为您解答：\n"
        "- Agent 经济商业模式\n"
        "- 平台服务接入流程\n"
        "- A2A 协议技术问题\n"
        "- 合作与投资机会\n\n"
        "请描述您的具体需求，我会给出专业建议。"
    )
