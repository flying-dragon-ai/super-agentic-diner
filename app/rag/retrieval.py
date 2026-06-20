"""Keyword RAG retrieval over the normalized product catalog.

Replaces the legacy ``coffee_kb`` reads. Positive terms recall via OR on the
product description/tags fields; negative terms are filtered out with NOT LIKE
to avoid the classic "否定词陷阱".
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Product


def retrieve(db: Session, positive, negative, top_k=3):
    """正向往量召回 + 负向 NOT LIKE 过滤，返回 Product 行。

    示例输入：
      positive = ["果香","柑橘","清甜"]
      negative = ["牛奶","奶","拿铁","奶香"]

    执行 SQL：
      SELECT * FROM product
      WHERE (description LIKE '%果香%' OR tags LIKE '%柑橘%' OR ...)   -> 正向召回
        AND description NOT LIKE '%牛奶%'                               -> 负向过滤
        AND description NOT LIKE '%拿铁%'
      LIMIT 3

    无正向词时返回空列表（交给 LLM 自行回答或反问）。
    """
    if not positive:
        return []

    pos_conds = []
    for w in positive:
        pos_conds.append(Product.description.like(f"%{w}%"))
        pos_conds.append(Product.tags.like(f"%{w}%"))
    query = db.query(Product).filter(or_(*pos_conds))

    if negative:
        neg_conds = []
        for w in negative:
            # 单字负向词（如"奶"）过于宽泛，会误伤描述里含"不加奶"的咖啡。
            # 所以只用长度>=2的明确成分词（如"牛奶""拿铁"）做确过滤。
            if len(w) < 2:
                continue
            neg_conds.append(Product.description.like(f"%{w}%"))
            neg_conds.append(Product.tags.like(f"%{w}%"))
        if neg_conds:
            query = query.filter(~or_(*neg_conds))

    return query.limit(top_k).all()
