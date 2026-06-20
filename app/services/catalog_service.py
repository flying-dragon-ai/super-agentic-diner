"""Product catalog lookup, option pricing, and stock management.

Products are the normalized menu + RAG source. Order placement routes stock
decrements through :func:`decrement_stock` (``SELECT ... FOR UPDATE``) and
refunds restore stock via :func:`restore_stock`.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Product
from app.domain_constants import (
    PRODUCT_STATUS_AVAILABLE,
    PRODUCT_STATUS_DISABLED,
    PRODUCT_STATUS_SOLD_OUT,
)


class CatalogError(Exception):
    pass


class AmbiguousProductError(CatalogError):
    """Multiple products match one query (e.g. 「冷萃」hits both 柑橘冷萃 and 椰香冷萃).

    Carries the candidate products so the caller can surface a "please specify
    which cup" prompt instead of silently picking one — which is what used to
    make the charged price diverge from the name the user thought they ordered.
    """

    def __init__(self, query: str, candidates: list[Product]) -> None:
        self.query = query
        self.candidates = candidates
        names = "、".join(p.name for p in candidates)
        super().__init__(f"「{query}」匹配到多杯：{names}，请明确要哪一杯")


class OutOfStockError(CatalogError):
    pass


def get_product_by_name(db: Session, name: str) -> Product | None:
    """Resolve a product by name with disambiguation.

    The menu is defined by exact product names (美式咖啡 / 柑橘冷萃 / ...). To
    tolerate colloquial short names (e.g. 「美式」→ 美式咖啡), a substring
    fallback is used **only when it matches exactly one product**. When the
    short name is ambiguous (e.g. 「冷萃」matches both 柑橘冷萃 and 椰香冷萃),
    :class:`AmbiguousProductError` is raised so the caller must ask the user
    to specify — we never silently pick a cup.
    """
    query = (name or "").strip()
    if not query:
        return None
    product = (
        db.query(Product)
        .filter(Product.name == query)
        .first()
    )
    if product:
        return product
    candidates = (
        db.query(Product)
        .filter(Product.name.like(f"%{query}%"))
        .order_by(Product.product_id.asc())
        .all()
    )
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise AmbiguousProductError(query, candidates)
    return None


def get_product(db: Session, product_id: int) -> Product | None:
    return db.query(Product).filter(Product.product_id == product_id).first()


def match_products_by_price(db: Session, price) -> list[Product]:
    """Price-exact product query (replaces the CoffeeKB price matcher)."""
    return db.query(Product).filter(Product.base_price == Decimal(str(price))).all()


def decrement_stock(
    db: Session, product_id: int, quantity: int
) -> Product:
    """Atomically decrement stock under a row lock.

    Raises :class:`OutOfStockError` if the product is disabled, sold out, or
    has insufficient stock. When the remainder hits 0 the product is marked
    ``sold_out``.
    """
    if quantity <= 0:
        raise CatalogError("quantity must be positive")
    product = db.execute(
        select(Product)
        .where(Product.product_id == product_id)
        .with_for_update()
    ).scalar_one_or_none()
    if product is None:
        raise CatalogError(f"product {product_id} not found")
    if product.status == PRODUCT_STATUS_DISABLED:
        raise CatalogError(f"product {product.name} is disabled")
    if product.stock is None or product.stock < quantity:
        raise OutOfStockError(
            f"{product.name} 库存不足：剩余 {product.stock or 0}，需要 {quantity}"
        )
    product.stock = product.stock - quantity
    if product.stock == 0:
        product.status = PRODUCT_STATUS_SOLD_OUT
    db.flush()
    return product


def restore_stock(db: Session, product_id: int, quantity: int) -> None:
    """Restore stock after a refund; flip sold_out back to available."""
    if quantity <= 0:
        return
    product = db.execute(
        select(Product)
        .where(Product.product_id == product_id)
        .with_for_update()
    ).scalar_one_or_none()
    if product is None:
        return
    current = product.stock or 0
    product.stock = current + quantity
    if product.status == PRODUCT_STATUS_SOLD_OUT:
        product.status = PRODUCT_STATUS_AVAILABLE
    db.flush()
