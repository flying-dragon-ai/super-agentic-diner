"""RAG-backed chat service for menu recommendations and product lookup."""
import re
import time
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Product
from app.llm import client as llm
from app.memory.chat_history import add_message, get_history
from app.rag.keywords import extract_keywords
from app.rag.retrieval import retrieve


# ===== 产品图片解析（按规则缩放说明：免责声明，5 张图出自 5 款基础咖啡，其余 9 款商品复用同品类最接近的图）=====
# 磁盘上 app/imag/ 只有 5 张 PNG(图片格式)：美式咖啡、柑橘冷萃、莓果拿铁、焦糖玛奇朵、椰香冷萃。
# 这些图片对应原始 coffee_kb(咖啡知识库) 5 款基础咖啡。后来 product(产品) 表扩到 14 款，
# 新增 9 款没有专属图。这里按"品类关键词"映射到同品类已有的图，避免 /imag/xxx.png 404 导致卡片裂图。
_IMAG_DIR = Path(__file__).resolve().parent.parent / "imag"
_DEFAULT_IMAGE = "美式咖啡.png"  # 兜底通用咖啡图（纯黑咖啡，最中性）

# 关键词→已有图片映射（按优先级，命中第一个即用）。映射依据：同品类视觉接近。
_IMAGE_KEYWORD_MAP = [
    ("美式", "美式咖啡.png"),       # 热美式 / 冰美式 → 美式图
    ("拿铁", "莓果拿铁.png"),       # 经典热拿铁 / 冰拿铁 / 秋日肉桂拿铁 → 拿铁图
    ("摩卡", "焦糖玛奇朵.png"),     # 热摩卡 → 甜系深色咖啡图
    ("焦糖", "焦糖玛奇朵.png"),
    ("玛奇朵", "焦糖玛奇朵.png"),
    ("卡布奇诺", "焦糖玛奇朵.png"), # 奶咖系 → 用最接近的奶咖图
    ("冷萃", "柑橘冷萃.png"),       # 冷萃系
    ("气泡", "柑橘冷萃.png"),       # 西西里气泡水（柑橘系）→ 柑橘冷萃图
    ("柠檬", "柑橘冷萃.png"),
    ("芒果", "柑橘冷萃.png"),       # 夏日芒芒特调（果香系）→ 果香冷萃图
    ("肉桂", "莓果拿铁.png"),       # 肉桂拿铁 → 拿铁图
]


def resolve_image_path(name: str) -> str:
    """把产品名解析成浏览器可用的图片 URL 路径。

    解析顺序：① 精确命中 app/imag/{name}.png（5 款基础咖啡走这条）
             ② 按品类关键词映射到同品类已有图（热美式→美式咖啡图 等）
             ③ 全部不命中则兜底通用咖啡图
    返回形如 /imag/xxx.png 的路径。
    """
    candidate = f"{name}.png"
    if (_IMAG_DIR / candidate).is_file():
        return f"/imag/{candidate}"
    for keyword, img in _IMAGE_KEYWORD_MAP:
        if keyword in name:
            return f"/imag/{img}"
    return f"/imag/{_DEFAULT_IMAGE}"


# ===== Product 表 TTL 缓存（菜单极少变化，避免每请求全表扫描）=====
_PRODUCT_CACHE: dict = {"data": None, "ts": 0.0}
_PRODUCT_CACHE_TTL = 60  # 秒


def get_all_products(db: Session) -> list[Product]:
    """获取全部 Product（按 base_price 排序），60 秒内走缓存。

    Product(产品) 表变更极少（仅下单扣库存），60s 缓存延迟可接受。
    """
    now = time.time()
    if _PRODUCT_CACHE["data"] is None or now - _PRODUCT_CACHE["ts"] > _PRODUCT_CACHE_TTL:
        _PRODUCT_CACHE["data"] = db.query(Product).order_by(Product.base_price).all()
        _PRODUCT_CACHE["ts"] = now
    return _PRODUCT_CACHE["data"]


def product_to_card(p: Product) -> dict:
    """序列化 Product(产品) 为前端图片卡片数据（与 /menu 格式一致）"""
    return {
        "name": p.name,
        "price": float(p.base_price),
        "tags": p.tags or "",
        "category": p.category or "",
        "description": (p.description or "")[:120],
        "image": resolve_image_path(p.name),
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
    no_match = not kb_rows
    if no_match or _is_browse_all(user_msg):
        kb_rows = get_all_products(db)

    # 第3步：把检索到的咖啡知识拼接成 context 字符串
    # 当 RAG 无召回时，前置一段提示告诉 LLM："顾客想要的可能不在菜单，请婉拒并推荐相似替代"，
    # 避免 LLM 闷头从全菜单里硬选，导致答非所问或像菜单广播器一样把全菜单列出来。
    menu_text = "\n---\n".join(
        f"{r.name}（¥{r.base_price}）：{r.description}" for r in kb_rows
    )
    if no_match and not _is_browse_all(user_msg):
        context = (
            "【RAG(检索) 注意】顾客描述的口味/品类没有精准命中菜单，下面是我们全部在售咖啡。"
            "请先用一句话承认「我们没有顾客提到的那个」，再从下面挑 1-2 款风味最接近的主动推荐。"
            "\n\n" + menu_text
        )
    else:
        context = menu_text

    # 第4步：调 LLM 生成回复（传入对话历史 + RAG检索到的真实资料）
    reply = llm.chat(history, user_msg, context)

    # 第5步：写回 Redis 记忆（本轮对话，供下一轮使用）
    add_message(user_id, "user", user_msg)
    add_message(user_id, "assistant", reply)
    return reply, [product_to_card(r) for r in kb_rows]
