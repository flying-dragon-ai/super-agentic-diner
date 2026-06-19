# ============================================================
# 【面试题·任务三】FastAPI 入口：聊天 + 下单接口
#
# 对应面试题任务三："就买你刚才推荐的那杯，从我余额里扣钱吧。"
# 后端处理流程（把 Redis、MySQL、LLM 串联）：
#
#   第1步：读 Redis 上下文（让 AI 知道"刚才推荐的那杯"是哪杯）
#   第2步：调 LLM 理解用户意图（是下单？推荐？闲聊？）
#   第3步：解析具体咖啡名（价格 → LLM引用 → RAG关键词 → 历史提取，4路优先级）
#   第4步：显示订单摘要，存入 Redis 待确认（两段式下单，防误扣）
#   第5步：用户确认后 → MySQL 事务内扣款（BEGIN → FOR UPDATE行锁 → 校验 → 扣+插 → COMMIT）
#   第6步：写回 Redis 记忆 + 返回话术
#
# 安全提示（面试题要求）：扣钱操作用事务+行锁保证安全性和顺序
# ============================================================
from typing import Optional

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import CoffeeKB, Order, User
from app.llm import client as llm
from app.memory.chat_history import (
    add_message,
    clear_pending_order,
    get_history,
    get_pending_order,
    set_pending_order,
)
from app.services.chat_service import extract_price, handle_message, match_by_price
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve
from app.services.order_service import (
    CoffeeNotResolvedError,
    InsufficientBalanceError,
    place_order,
    place_orders,
)

app = FastAPI(title="智能咖啡馆 AI 店长")

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _resolve_coffees_from_history(db, history, max_messages=1):
    """【任务三·第3步】从 Redis 历史消息中提取被推荐过的咖啡名。

    对应面试题：用户说"就买你刚才推荐的那杯"→ 需要从对话历史解析出具体咖啡名。

    max_messages=1：只看最近1条assistant消息（默认，避免前面聊过5杯就全选）
    max_messages=3：看最近3条（用户说"这两杯了"时用，跨多轮提取）
    """
    all_coffees = [c.coffee_name for c in db.query(CoffeeKB).all()]
    found = []
    msg_count = 0
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            msg_count += 1
            if msg_count > max_messages:
                break
            for name in all_coffees:
                if name in msg.get("content", "") and name not in found:
                    found.append(name)
    return found


def _lookup_price_from_kb(db, coffee_name):
    """从知识库查价格，查不到返回 0"""
    kb = db.query(CoffeeKB).filter(CoffeeKB.coffee_name == coffee_name).first()
    return float(kb.price) if kb else 0.0


# 待确认订单时，用户确认的触发词（LLM 优先，这是关键字的底层兜底）
_CONFIRM_WORDS = (
    "确认", "下单", "好的", "好", "对", "是的", "没错",
    "买", "可以", "行", "就下单", "下单吧", "结账",
    "没错下单", "对了下单",
)


def _is_confirming(user_msg):
    """判断用户是否在确认待支付订单。
    用 startswith 而非 in，避免「不对」被「对」误判。
    """
    msg = user_msg.strip()
    if len(msg) <= 6:
        return any(msg.startswith(w) for w in _CONFIRM_WORDS)
    return False


# 修改/取消订单的信号词
_MODIFY_WORDS = (
    "只要", "不要", "换", "改", "改成", "换成",
    "去掉", "太多了", "错了", "不对", "不是",
    "来个", "来杯", "给我来", "帮我来",
)


def _is_modifying(user_msg):
    """判断用户是否在修改/重新选择待确认订单"""
    return any(w in user_msg for w in _MODIFY_WORDS)


class ChatRequest(BaseModel):
    user_id: int
    message: str
    request_id: Optional[str] = None  # 可选，下单幂等键


class ChatResponse(BaseModel):
    reply: str
    order_id: Optional[int] = None


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """【面试题·任务三·完整流程】聊天/下单主接口

    当用户发来 "就买你刚才推荐的那杯，从我余额里扣钱吧。" 时：
    第1步：读 Redis 上下文 → 知道"刚才推荐的那杯"是什么
    第2步：调 LLM → 理解用户意图（下单确认）
    第3步：解析咖啡名 → 价格/LLM/RAG/历史 四路优先
    第4步：显示摘要 → 存 Redis 待确认（两段式防误扣）
    第5步：用户回复"确认" → MySQL 事务扣款
    第6步：写 Redis 记忆 + 返回话术
    """
    # ===== 第1步：读 Redis 上下文（短期记忆，最近5轮对话）=====
    history = get_history(req.user_id)

    # ===== 第0步：检查 Redis 是否有待确认订单（两段式下单）=====
    pending = get_pending_order(req.user_id)

    if pending:
        # --- 有待确认订单：判断用户是确认还是修改 ---
        if _is_confirming(req.message):
            # 用户明确回复了确认词（"确认"/"下单"/"好"等）→ 执行扣款
            try:
                items = [(item["name"], req.request_id if i == 0 else None)
                         for i, item in enumerate(pending["coffees"])]
                orders = place_orders(db, req.user_id, items)
            except InsufficientBalanceError as e:
                clear_pending_order(req.user_id)
                reply = f"下单失败：{e}。请先充值哦~"
                add_message(req.user_id, "user", req.message)
                add_message(req.user_id, "assistant", reply)
                return ChatResponse(reply=reply)

            clear_pending_order(req.user_id)
            user = db.query(User).filter(User.user_id == req.user_id).first()
            balance = user.balance if user else "?"
            if len(orders) == 1:
                reply = (
                    f"好嘞！已为您下单「{orders[0].coffee_name}」，扣款 ¥{orders[0].amount}，"
                    f"当前余额 ¥{balance}。祝您品尝愉快~"
                )
            else:
                order_lines = "\n".join(f"  • {o.coffee_name} ¥{o.amount}" for o in orders)
                total = sum(o.amount for o in orders)
                reply = (
                    f"好嘞！已为您下单 {len(orders)} 杯：\n{order_lines}\n"
                    f"合计 ¥{total}，当前余额 ¥{balance}。祝您品尝愉快~"
                )
            add_message(req.user_id, "user", req.message)
            add_message(req.user_id, "assistant", reply)
            return ChatResponse(reply=reply, order_id=orders[0].order_id)
        else:
            # 不是纯确认词 → 清掉待确认，落入下方正常流程重新处理
            # （覆盖：修改订单"只要28的"、换一杯、重新选、闲聊等所有情况）
            clear_pending_order(req.user_id)

    # ===== 第2步：无待确认订单 → 调 LLM 理解用户意图 =====
    # LLM 返回三分类之一：order（下单）/ recommend（求推荐）/ chat（闲聊）
    intent = llm.parse_intent(history, req.message)

    # ===== 第3步：LLM 判断为"下单"意图 → 解析具体是哪杯咖啡 =====
    # 四路优先级：价格匹配 > LLM显式名 > RAG关键词 > 历史提取
    if intent.get("intent") == "order":
        coffees = []

        # 第3.1路：价格匹配（"来个28元的"→ 按价格查 MySQL CoffeeKB）
        price = extract_price(req.message)
        if price is not None:
            coffees = [c.coffee_name for c in match_by_price(db, price)]

        # 第3.2路：LLM 显式给出了咖啡名（它能理解"一开始说的""刚才那杯"等引用）
        # 信任 LLM 的引用理解能力，排在历史盲扫之前
        if not coffees:
            coffee = intent.get("coffee_name")
            if coffee:
                # 处理 LLM 可能返回合并名 "柑橘冷萃和美式咖啡"
                valid_names = [c.coffee_name for c in db.query(CoffeeKB).all()]
                parts = [p.strip() for p in coffee.replace("和", ",").replace("、", ",").split(",") if p.strip()]
                matched = [p for p in parts if p in valid_names]
                if matched:
                    coffees = matched

        # 第3.3路：消息含描述性词（"无牛奶"/"果味"）→ RAG 关键词过滤
        if not coffees:
            positive, negative = extract_keywords(req.message)
            if positive or negative:
                coffees = [r.coffee_name for r in retrieve(db, positive, negative)]

        # 第3.4路：以上都没命中 → 从 Redis 历史提取（最弱信号，兜底）
        # 默认只看最近1条消息（1杯）；用户说「两杯/这些/都」时跨轮提取3条
        _MULTI_SIGNALS = ("两杯", "这些", "都", "全部", "三个", "两个", "这几杯", "都来", "全要")
        wants_multi = any(w in req.message for w in _MULTI_SIGNALS)
        if not coffees:
            scan = 3 if wants_multi else 1
            coffees = _resolve_coffees_from_history(db, history, max_messages=scan)

        # 默认只取 1 杯，除非明确说了多杯信号
        if len(coffees) > 1 and not wants_multi:
            coffees = coffees[:1]

        if not coffees:
            reply = "不好意思，我没太确定您想买哪杯，能再说一下咖啡名字吗？"
            add_message(req.user_id, "user", req.message)
            add_message(req.user_id, "assistant", reply)
            return ChatResponse(reply=reply)

        # ===== 第4步：两段式下单 —— 先存 Redis 待确认，显示摘要（不直接扣款）=====
        # 把选中的咖啡名+价格存入 Redis，等用户回复"确认"后才执行扣款
        items = []
        for name in coffees:
            p = _lookup_price_from_kb(db, name)
            items.append({"name": name, "price": p})
        total = sum(i["price"] for i in items)
        set_pending_order(req.user_id, {"coffees": items, "total": total})

        lines = "\n".join(f"  • {i['name']}  ¥{i['price']:.2f}" for i in items)
        reply = (
            f"收到！您点的是：\n{lines}\n"
            f"合计 ¥{total:.2f}\n"
            f"确认下单请回复「确认」或「下单」~"
        )
        add_message(req.user_id, "user", req.message)
        add_message(req.user_id, "assistant", reply)
        return ChatResponse(reply=reply)

    # ===== 非下单意图（recommend/chat）→ 走 RAG 聊天流程 =====
    # handle_message 内部：读Redis → 关键词提取 → LIKE检索 → LLM生成 → 写Redis
    clear_pending_order(req.user_id)
    reply = handle_message(db, req.user_id, req.message)
    return ChatResponse(reply=reply)


@app.get("/user/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(404, "用户不存在")
    return {
        "user_id": user.user_id,
        "nickname": user.nickname,
        "balance": float(user.balance),
        "taste_preference": user.taste_preference,
    }


@app.get("/history/{user_id}")
def get_chat_history(user_id: int):
    return get_history(user_id)


@app.delete("/history/{user_id}")
def clear_chat_history(user_id: int):
    from app.memory.chat_history import clear_history

    clear_history(user_id)
    return {"ok": True}


@app.get("/orders/{user_id}")
def list_orders(user_id: int, db: Session = Depends(get_db)):
    """返回某用户的订单列表（最近 10 单），供网页侧栏展示"""
    rows = (
        db.query(Order)
        .filter(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "order_id": o.order_id,
            "coffee_name": o.coffee_name,
            "amount": float(o.amount),
            "status": o.status,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for o in rows
    ]


@app.get("/status")
def status():
    """返回系统状态：数据库模式、记忆模式、LLM 是否真实接入"""
    from app.config import settings

    return {
        "db_mode": settings.db_mode,
        "memory_mode": settings.memory_mode,
        "llm_active": llm.has_real_key(),
    }


@app.get("/")
def index():
    """根路由：返回聊天网页"""
    return FileResponse(_STATIC_DIR / "index.html")
