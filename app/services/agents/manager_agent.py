"""店长 Agent(总调度)：意图分析 + 纠正/生气/重复信号检测。

职责：
  1. 意图分析（order / recommend / chat）—— 复用现有 parse_intent
  2. 纠正检测——用户表达「不是我要的 / 判断失误」时触发复盘 Agent
  3. 生气检测——用户表达不满/愤怒情绪时触发复盘 Agent（服务体验差）
  4. 重复检测——用户连续两次说同样的话时触发复盘 Agent（AI 没理解）
"""
from __future__ import annotations

from app.llm import client as llm

# 纠正信号词：出现这些词且历史里有推荐记录 → 判定为 AI(人工智能) 判断失误，触发复盘
CORRECTION_WORDS = (
    "不是", "不对", "错了", "你理解错", "我说的不是", "我说的是",
    "不要这个", "换一个", "不是这个味", "不是我要的",
    "听错了", "搞错了", "认错了", "判断错",
)

# 疑问/澄清不算纠正（如"是不是？""不是吧？"）
CORRECTION_QUESTION_MARKS = ("？", "?", "吗", "嘛", "吧")

# 生气/不满信号词：出现即视为用户情绪恶化，触发复盘改善体验
ANGER_WORDS = (
    "烦死", "太烂", "垃圾", "什么破", "浪费时间", "受不了",
    "有没有搞错", "无语", "差评", "投诉", "退款", "什么态度",
    "脑子有病", "智障", "蠢", "笨", "你到底", "能不能行",
    "都说了", "跟你说了", "说了几遍", "听不懂人话",
    "气死", "恶心", "离谱", "可笑",
)

# 重复检测的强度阈值（相似度 0-1，超过则判定为重复）
REPEAT_SIMILARITY_THRESHOLD = 0.7


def parse_intent(history, user_msg: str) -> dict:
    """意图分析：委托给 llm.parse_intent（复用现有三分类逻辑）。"""
    return llm.parse_intent(history, user_msg)


def detect_correction(user_msg: str, history: list[dict]) -> bool:
    """检测用户是否在纠正 AI(人工智能) 的上一轮推荐。

    判定条件（同时满足）：
      1. 用户消息含纠正信号词；
      2. 历史里最近 1-2 条 assistant(助手) 消息包含咖啡推荐（出现过咖啡名或「推荐」字样）；
      3. 不是疑问句（排除「是不是？」「不是吧？」等澄清语气）。

    这样既不会把闲聊误判为纠正，也能捕获「不对，我想要更苦的」这类隐式纠正。
    """
    msg = user_msg.strip()
    if not msg:
        return False
    # 疑问句不视为纠正
    if any(m in msg for m in CORRECTION_QUESTION_MARKS):
        return False
    # 必须含纠正词
    if not any(w in msg for w in CORRECTION_WORDS):
        return False
    # 历史里必须有过推荐（assistant 消息含咖啡名或「推荐」字样）
    recent_bot = [
        m.get("content", "")
        for m in (history or [])
        if m.get("role") == "assistant"
    ][:2]
    has_recommendation = any(
        "推荐" in c or "拿铁" in c or "美式" in c or "冷萃" in c
        or "摩卡" in c or "咖啡" in c
        for c in recent_bot
    )
    return has_recommendation


def detect_anger(user_msg: str) -> bool:
    """检测用户是否在表达生气/不满情绪。

    只看当前消息是否含生气信号词。不做历史判断（情绪是当下的）。
    生气通常意味着 AI 的推荐或对话体验出了问题，需要复盘改善。
    """
    msg = user_msg.strip()
    if not msg:
        return False
    return any(w in msg for w in ANGER_WORDS)


def _text_similarity(a: str, b: str) -> float:
    """简易文本相似度：基于 2-gram Jaccard(交集/并集) 计算 0-1 的相似度。

    不依赖外部库，用字符级 bigram 做快速近似。
    完全相同=1.0，完全不同=0.0。
    """
    a = a.strip()
    b = b.strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # 极短文本直接比较
    if len(a) <= 4 or len(b) <= 4:
        return 1.0 if a == b else 0.0
    # 字符级 bigram
    def bigrams(text: str) -> set[str]:
        return {text[i:i + 2] for i in range(len(text) - 1)}
    ba = bigrams(a)
    bb = bigrams(b)
    if not ba or not bb:
        return 0.0
    intersection = ba & bb
    union = ba | bb
    return len(intersection) / len(union) if union else 0.0


def detect_repeat(user_msg: str, history: list[dict]) -> bool:
    """检测用户是否连续两次说了同样/高度相似的话。

    判定条件：
      1. 取历史里最近 1 条 user(用户) 消息；
      2. 与当前消息做相似度比较；
      3. 相似度超过阈值（0.7） → 判定为重复，说明 AI 上一轮没理解用户。

    例：用户说"我要苦的"→ AI 推荐了甜的 → 用户再说"我要苦的"→ 重复触发。
    """
    msg = user_msg.strip()
    if not msg or len(msg) < 2:
        return False
    # 取最近 1 条历史 user 消息
    recent_user = [
        m.get("content", "")
        for m in (history or [])
        if m.get("role") == "user"
    ][:1]
    if not recent_user:
        return False
    prev = recent_user[0].strip()
    if not prev:
        return False
    return _text_similarity(msg, prev) >= REPEAT_SIMILARITY_THRESHOLD


def detect_review_trigger(user_msg: str, history: list[dict]) -> tuple[bool, str]:
    """统一检测是否需要触发复盘 Agent，返回 (是否触发, 触发原因)。

    按优先级检测三种信号：
      1. 纠正信号（detect_correction）— reason="correction"
      2. 生气信号（detect_anger）— reason="anger"
      3. 重复信号（detect_repeat）— reason="repeat"

    任一命中即触发。
    """
    if detect_correction(user_msg, history):
        return True, "correction"
    if detect_anger(user_msg):
        return True, "anger"
    if detect_repeat(user_msg, history):
        return True, "repeat"
    return False, ""
