"""店长 Agent(总调度)：意图分析 + 纠正信号检测。

职责：
  1. 意图分析（order / recommend / chat）—— 复用现有 parse_intent
  2. 纠正检测——用户表达「不是我要的 / 判断失误」时触发复盘 Agent
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
