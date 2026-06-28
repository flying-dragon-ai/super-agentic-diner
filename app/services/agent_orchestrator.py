"""Agent 编排器：按序协调店长 / 推荐 / 复盘 / 经验继承四个 Agent。

被 /chat 调用，替代原来直接调 parse_intent + chat_service 的散装逻辑。
编排流程：
  1. 店长 Agent 意图分析 → order / recommend / chat
  2. 检测纠正信号 → 若是，复盘 Agent 后台异步执行（不阻塞推荐响应）
  3. recommend → 推荐 Agent（融合经验）生成回复
  4. chat → 复用推荐 Agent（闲聊也能给点建议）
  5. order → 不在此处理，返回意图由 main.py 继续下单流程

返回 OrchestratorResult，main.py 据此执行下单 / 回复 + 发可视化事件。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Product
from app.llm import client as llm
from app.memory.chat_history import add_message, get_history
from app.services.agents import manager_agent, recommender_agent, reviewer_agent
from app.services.chat_service import product_to_card, _is_browse_all, get_all_products

logger = logging.getLogger(__name__)


# 触发复盘（纠正/生气/重复）后给用户的统一道歉回复。
# 用户诉求：检测到不满 → 复盘完成 → 回复道歉语（而非继续推下一款）。
APOLOGY_REPLY = "很抱歉给您带来了不好的体验，我已将这次问题上传复盘，下次会做得更好～"


def _extract_products_from_reply(db: Session, reply: str) -> list[dict]:
    """从 LLM 回复文本中提取提到的咖啡名，生成产品卡片。

    扫描 reply 中出现的每个 Product 名（全名匹配），
    返回匹配到的产品卡片列表（去重，保持首次出现顺序）。
    """
    if not reply:
        return []
    all_products = get_all_products(db)
    cards = []
    seen = set()
    for p in all_products:
        if p.name in reply and p.name not in seen:
            cards.append(product_to_card(p))
            seen.add(p.name)
    return cards


def _emit_now(emit, event_type: str, payload: dict) -> None:
    """实时推送 agent 事件（如果有 emit 回调）。

    emit: 可选的可调用对象，签名 emit(event_type, payload_dict)。
    没传 emit 时只记录到 result.events（兼容旧批量发布路径）。
    """
    if emit:
        try:
            emit(event_type, payload)
        except Exception:
            logger.warning("实时推送 agent 事件失败 type=%s", event_type, exc_info=True)


def _detect_exact_product(db: Session, user_msg: str) -> str | None:
    """检测用户消息是否包含精确的咖啡商品名。

    如"我要一杯柑橘冷萃" → 返回 "柑橘冷萃"。
    也支持部分匹配："美式" → "美式咖啡"，"拿铁" → "莓果拿铁"。
    仅当唯一匹配时返回（"冷萃"同时匹配柑橘冷萃+椰香冷萃 → 不返回）。
    """
    all_products = get_all_products(db)
    # 1. 全名匹配（最高优先级，无歧义）
    for p in all_products:
        if p.name in user_msg:
            return p.name
    # 2. 部分匹配：商品名去掉通用后缀后是用户消息的子串
    #    如 "美式咖啡"→"美式"、"焦糖玛奇朵"→"焦糖"（去"咖啡"后缀后匹配）
    matches = []
    for p in all_products:
        # 取商品名的核心部分（去掉"咖啡"后缀）
        cores = set()
        cores.add(p.name)  # 全名本身
        if p.name.endswith("咖啡"):
            cores.add(p.name[:-2])  # 美式咖啡 → 美式
        for core in cores:
            if len(core) >= 2 and core != p.name and core in user_msg:
                matches.append(p.name)
                break
    # 唯一匹配才返回，多个匹配表示歧义（如"冷萃"→柑橘冷萃+椰香冷萃）
    if len(matches) == 1:
        return matches[0]
    # 3. 用户消息中的 2 字词出现在商品名里（如"拿铁"在"莓果拿铁"中）
    #    不歧义时（只匹配一款）即可返回；歧义时（"冷萃"匹配两款）返回 None
    single_token_matches = []
    _SKIP = {"咖啡"}  # 过于通用，跳过
    for p in all_products:
        for i in range(len(user_msg) - 1):
            substr = user_msg[i:i+2]
            if len(substr) >= 2 and substr not in _SKIP and substr in p.name:
                if p.name not in single_token_matches:
                    single_token_matches.append(p.name)
                break
    if len(single_token_matches) == 1:
        return single_token_matches[0]
    return None


@dataclass
class OrchestratorResult:
    """编排器返回给 /chat 的结构化结果。"""

    intent: str = "chat"
    reply: str = ""
    # Agent 协作元数据（供 main.py 发可视化事件）
    events: list[dict[str, Any]] = field(default_factory=list)
    # 复盘结果（检测到纠正时填充）
    review: dict[str, Any] | None = None
    applied_experience: bool = False
    # 推荐/聊天路径涉及的产品卡片数据（供前端图片卡片渲染）
    products: list[dict] = field(default_factory=list)


def orchestrate(
    db: Session,
    user_id: int,
    user_msg: str,
    *,
    correlation_id: str | None = None,
    precomputed_intent: dict | None = None,
    emit=None,
) -> OrchestratorResult:
    """多 Agent(智能体) 协作主入口。

    参数 precomputed_intent：如果 main.py 已经调过 parse_intent，传入结果避免重复 LLM 调用。
    参数 emit：可选的事件回调 emit(event_type, payload_dict)，用于实时推送 agent 事件
              （让前端灯在思考期间跟随执行节奏点亮，而非响应返回前批量推送）。
    副作用：会写 Redis 对话历史（add_message），与原 /chat 行为一致。
    """
    result = OrchestratorResult()
    history = get_history(user_id)

    # ===== 快速检测：消息含精确商品名 → 直接 order，跳过所有 LLM 调用 =====
    exact_product = _detect_exact_product(db, user_msg)
    if exact_product:
        result.intent = "order"
        result.events.append(
            {
                "type": "agent.manager.intent",
                "payload": {"user_id": user_id, "intent": "order", "reason": f"exact_product:{exact_product}"},
            }
        )
        _emit_now(emit, "agent.manager.intent", result.events[-1]["payload"])
        return result

    # ===== 第1步：店长 Agent 意图分析 =====
    # 如果 main.py 已经分析过意图，直接复用（省掉一次 LLM 调用，加速响应）
    if precomputed_intent:
        intent_data = precomputed_intent
    else:
        intent_data = manager_agent.parse_intent(history, user_msg)
    intent = intent_data.get("intent", "chat")
    result.intent = intent
    result.events.append(
        {
            "type": "agent.manager.intent",
            "payload": {"user_id": user_id, "intent": intent, "reason": intent_data.get("reason", "")},
        }
    )
    _emit_now(emit, "agent.manager.intent", result.events[-1]["payload"])

    # ===== 第2步：纠正/生气/重复检测 → 同步复盘 Agent + 回复道歉语（短路，不再推下一款） =====
    # 用户诉求：检测到不满信号 → 先完成复盘（总结）→ 再回复道歉语。
    # 因此这里同步执行复盘（best-effort：失败也照常道歉），而非原先的后台线程。
    triggered, trigger_reason = manager_agent.detect_review_trigger(user_msg, history)
    if triggered:
        result.events.append(
            {
                "type": "agent.reviewer.reviewing",
                "payload": {"user_id": user_id, "trigger": trigger_reason},
            }
        )
        _emit_now(emit, "agent.reviewer.reviewing", result.events[-1]["payload"])
        # 同步执行复盘（独立逻辑，失败 swallow 不影响道歉回复）
        review_result = None
        try:
            review_result = reviewer_agent.review_mistake(
                db,
                user_id=user_id,
                user_msg=user_msg,
                history=list(history),
                correlation_id=correlation_id,
                trigger_reason=trigger_reason,
            )
        except Exception:
            logger.warning("复盘 Agent(事后复盘) 执行失败", exc_info=True)
        result.review = review_result
        result.events.append(
            {
                "type": "agent.reviewer.reviewed",
                "payload": {
                    "user_id": user_id,
                    "trigger": trigger_reason,
                    "has_insight": bool(review_result),
                },
            }
        )
        _emit_now(emit, "agent.reviewer.reviewed", result.events[-1]["payload"])
        # 复盘完成 → 回复道歉语，写历史，直接返回（不走后续推荐/闲聊）
        result.reply = APOLOGY_REPLY
        add_message(user_id, "user", user_msg)
        add_message(user_id, "assistant", result.reply)
        return result

    # ===== 第3步：按意图分派 =====
    if intent == "order":
        # order 意图不在此处理回复，main.py 继续走下单流程
        return result

    if intent == "recommend":
        # 推荐 Agent：RAG + 经验融合 → 生成推荐
        result.events.append(
            {
                "type": "agent.recommender.suggesting",
                "payload": {"user_id": user_id},
            }
        )
        _emit_now(emit, "agent.recommender.suggesting", result.events[-1]["payload"])
        reco = recommender_agent.recommend(db, user_id, user_msg, history)
        result.reply = reco["reply"]
        result.applied_experience = reco["applied_experience"]
        # 看菜单请求：卡片展示全部产品；否则从回复文本提取提到的咖啡名生成卡片
        if _is_browse_all(user_msg):
            all_products = get_all_products(db)
            result.products = [product_to_card(p) for p in all_products]
        else:
            result.products = _extract_products_from_reply(db, reco["reply"])
        result.events.append(
            {
                "type": "agent.recommender.suggested",
                "payload": {
                    "user_id": user_id,
                    "applied_experience": reco["applied_experience"],
                    "candidate_count": len(reco["candidates"]),
                    "hard_filtered": reco.get("hard_filtered", []),
                },
            }
        )
        _emit_now(emit, "agent.recommender.suggested", result.events[-1]["payload"])
        if reco["applied_experience"]:
            result.events.append(
                {
                    "type": "agent.experience.applied",
                    "payload": {"user_id": user_id},
                }
            )
            _emit_now(emit, "agent.experience.applied", result.events[-1]["payload"])
        # 写对话历史
        add_message(user_id, "user", user_msg)
        add_message(user_id, "assistant", result.reply)
        return result

    # ===== chat 意图：用店长人设闲聊（含桥接规则），不走推荐 Agent =====
    # chat 用 SYSTEM_PROMPT（有性格+桥接规则），传简短菜单列表（不是完整 RAG context）
    _menu_brief = "、".join(f"{p.name}（¥{p.base_price}）" for p in get_all_products(db))
    result.reply = llm.chat(history, user_msg, f"今日菜单：{_menu_brief}")
    result.applied_experience = False
    # chat 意图：只在用户明确要看菜单时弹卡片；纯闲聊不弹
    if _is_browse_all(user_msg):
        all_products = db.query(Product).order_by(Product.base_price).all()
        result.products = [product_to_card(p) for p in all_products]
    result.events.append(
        {
            "type": "agent.recommender.suggested",
            "payload": {
                "user_id": user_id,
                "intent": "chat",
                "applied_experience": False,
            },
        }
    )
    _emit_now(emit, "agent.recommender.suggested", result.events[-1]["payload"])
    add_message(user_id, "user", user_msg)
    add_message(user_id, "assistant", result.reply)
    return result
