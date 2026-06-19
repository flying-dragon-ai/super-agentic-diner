# ============================================================
# 【面试题·任务二·2】关键词 RAG 召回模块
#
# 对应面试题：
#   任务二·2：如何避开"否定词陷阱"？
#     → 正向词用 LIKE 召回候选（OR 扩大召回面）
#     → 负向词用 NOT LIKE 过滤掉含奶饮品（AND 剔除）
#
# SQL 等价逻辑：
#   SELECT * FROM coffee_kb
#   WHERE (content LIKE '%果香%' OR tags LIKE '%柑橘%')      ← 正向召回
#     AND content NOT LIKE '%牛奶%' AND content NOT LIKE '%拿铁%'  ← 负向过滤
# ============================================================
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import CoffeeKB


def retrieve(
    db: Session, positive, negative, top_k=3
):
    """【任务二·2】用正向词 OR 召回候选段落，再用负向词 NOT LIKE 过滤掉不该出现的。

    示例输入：
      positive = ["果香","柑橘","清甜"]
      negative = ["牛奶","奶","拿铁","奶香"]

    执行 SQL：
      SELECT * FROM coffee_kb
      WHERE (content LIKE '%果香%' OR tags LIKE '%柑橘%' OR ...)   ← 正向召回
        AND content NOT LIKE '%牛奶%'                               ← 负向过滤
        AND content NOT LIKE '%拿铁%'
      LIMIT 3

    无正向词时返回空列表（交由 LLM 自行回答或反问）。
    """
    if not positive:
        return []

    # 【任务二·2】第一步：用正向词 OR 条件召回候选段落
    # 在 content（正文）和 tags（标签）两个字段上 LIKE 匹配，扩大召回面
    pos_conds = []
    for w in positive:
        pos_conds.append(CoffeeKB.content.like(f"%{w}%"))
        pos_conds.append(CoffeeKB.tags.like(f"%{w}%"))
    query = db.query(CoffeeKB).filter(or_(*pos_conds))

    # 【任务二·2】第二步：用负向词 NOT LIKE 过滤掉不该推荐的段落
    # 这就是避开"否定词陷阱"的核心：用户说"不要牛奶"，就把含牛奶的段落剔除
    if negative:
        neg_conds = []
        for w in negative:
            # 【重要】单字负向词（如"奶"）过于宽泛，会误伤描述里含"不加奶"的咖啡
            # 例如柑橘冷萃描述里有"不加糖不加奶"，如果用 NOT LIKE '%奶%' 会把它误杀
            # 所以只用长度>=2的明确成分词（如"牛奶""拿铁"）做硬过滤
            if len(w) < 2:
                continue
            neg_conds.append(CoffeeKB.content.like(f"%{w}%"))
            neg_conds.append(CoffeeKB.tags.like(f"%{w}%"))
        # 用 ~or_ 即 NOT (OR ...) 剔除命中任一明确负向成分词的段落
        if neg_conds:
            query = query.filter(~or_(*neg_conds))

    return query.limit(top_k).all()
