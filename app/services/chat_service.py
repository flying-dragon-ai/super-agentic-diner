"""RAG-backed chat service for menu recommendations and product lookup."""
import re

from sqlalchemy.orm import Session

from app.db.models import Product
from app.llm import client as llm
from app.memory.chat_history import add_message, get_history
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve


def product_to_card(p: Product) -> dict:
    """序列化 Product(产品) 为前端图片卡片数据（与 /menu 格式一致）"""
    return {
        "name": p.name,
        "price": float(p.base_price),
        "tags": p.tags or "",
        "category": p.category or "",
        "description": (p.description or "")[:120],
        "image": f"/imag/{p.name}.png",
        "stock": p.stock,
    }

# 用户想看更多/全部产品时的触发词（注意："套餐"不在此列，它是组合套餐≠全部单品）
_BROWSE_ALL_WORDS = (
    "还有", "还有什么", "还有吗", "列出", "全部", "所有", "全列",
    "还有什么品类", "品类", "菜单", "还有什么推荐", "还有哪些",
    "都列出来", "列出来", "有什么咖啡", "查看所有", "查看全部", "所有类型",
)

# 价格匹配正则：28元 / ¥28 / 28块 / 28的
_PRICE_PATTERNS = [
    re.compile(r"(\d+)\s*元"),
    re.compile(r"(\d+)\s*块"),
    re.compile(r"[¥￥]\s*(\d+)"),
    re.compile(r"(\d+)\s*的"),
]


def _is_browse_all(text):
    return any(w in text for w in _BROWSE_ALL_WORDS)


def extract_price(text):
    """从文本中提取价格数字，无则返回 None。如 "来个28元的" → 28"""
    for pat in _PRICE_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


def match_by_price(db, price):
    """按价格精确查询商品，返回 Product 列表"""
    return db.query(Product).filter(Product.base_price == price).all()


def handle_message(db, user_id, user_msg):
    """【任务二】聊天主流程：读记忆 → RAG检索 → LLM生成 → 写记忆

    用户消息示例："店长，我想喝点清甜水果味的，但不要加牛奶，推荐一下。"

    执行步骤：
    第1步：读 Redis 短期记忆（最近5轮对话，让AI有上下文）
    第1.5步：检测价格查询（"28元"→ 按价格查MySQL，不走关键词RAG）
    第2步：关键词提取（jieba分词 + 去停用词 + 同义词扩展 + 否定词分离）
           → positive=["清甜","果香",...] negative=["牛奶","拿铁",...]
    第3步：RAG检索（正向LIKE召回 + 负向NOT LIKE过滤）
    第3.5步：RAG无结果 或 用户问"还有什么" → 加载全部真实产品（防LLM幻觉）
    第4步：调LLM（把检索到的咖啡知识作为上下文，让AI基于真实资料回复）
    第5步：写回Redis记忆（本轮对话，供下一轮使用）
    """

    # 第1步：读 Redis 短期记忆（最近5轮对话，让 AI 有上下文）
    history = get_history(user_id)

    # 第1.5步：检测价格查询（如"有没有28元的"）→ 按价格直接查 MySQL，不走关键词RAG
    price = extract_price(user_msg)
    if price is not None:
        kb_rows = match_by_price(db, price)
        if kb_rows:
            context = "\n---\n".join(
                f"{r.name}（¥{r.base_price}）：{r.description}" for r in kb_rows
            )
            reply = llm.chat(history, user_msg, context)
            add_message(user_id, "user", user_msg)
            add_message(user_id, "assistant", reply)
            return reply, [product_to_card(r) for r in kb_rows]

    # 第2步：【任务二·1】关键词提取 + RAG 检索
    # extract_keywords: jieba分词→去停用词→同义词扩展→否定词分离
    #   positive=["清甜","果香",...] negative=["牛奶","拿铁",...]
    # retrieve: 正向词LIKE召回 + 负向词NOT LIKE过滤（避开否定词陷阱）
    positive, negative = extract_keywords(user_msg)
    kb_rows = retrieve(db, positive, negative)

    # 第2.5步：RAG 无结果 或 用户想看全部 → 加载所有真实产品，杜绝 LLM 幻觉
    # （不加载的话 LLM 会编造不存在的咖啡，如"危地马拉手冲""澳白"）
    if not kb_rows or _is_browse_all(user_msg):
        kb_rows = db.query(Product).order_by(Product.base_price).all()

    # 第3步：把检索到的咖啡知识拼接成 context 字符串
    context = "\n---\n".join(
        f"{r.name}（¥{r.base_price}）：{r.description}" for r in kb_rows
    )

    # 第4步：调 LLM 生成回复（传入对话历史 + RAG检索到的真实资料）
    reply = llm.chat(history, user_msg, context)

    # 第5步：写回 Redis 记忆（本轮对话，供下一轮使用）
    add_message(user_id, "user", user_msg)
    add_message(user_id, "assistant", reply)
    return reply, [product_to_card(r) for r in kb_rows]
