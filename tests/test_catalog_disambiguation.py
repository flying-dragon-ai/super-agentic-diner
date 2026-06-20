"""Regression tests for catalog name disambiguation.

Locks the fix for the bug where a short/ambiguous name (e.g. 「冷萃」) silently
matched the cheapest cup via LIKE + ``.first()``, so the charged price diverged
from the cup the user thought they ordered. ``get_product_by_name`` must now:

  * hit on exact name
  * accept a substring only when it matches exactly one product
  * raise ``AmbiguousProductError`` on multi-match (never silently pick one)
  * return None when nothing matches

and ``resolve_line`` must translate that ambiguity into an ``OrderError`` so
the chat flow asks the user to specify instead of charging the wrong cup.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy import text

from app.db.database import SessionLocal
from app.db.models import Product
from app.services.catalog_service import (
    AmbiguousProductError,
    get_product_by_name,
)
from app.services.order_service import OrderError, resolve_line


def _mysql_reachable() -> bool:
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_mysql_reachable(), "MySQL not reachable")
class CatalogDisambiguationTests(unittest.TestCase):
    """Seeds two products sharing a substring (ambiguous) plus one unique
    product, then tears them down so the real menu is untouched. A distinctive
    PREFIX keeps these rows isolated from the seed catalog (柑橘冷萃 / 椰香冷萃
    / 美式咖啡 / ...) so substring queries only hit the test rows."""

    PREFIX = "测试DISAM"

    def setUp(self):
        self.db = SessionLocal()
        # Purge leftovers from an interrupted previous run.
        self.db.query(Product).filter(Product.sku.like(f"{self.PREFIX}-%")).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.p_cold_a = Product(
            sku=f"{self.PREFIX}-A",
            name=f"{self.PREFIX}冷萃A",
            category="冷萃",
            description="disambiguation test A",
            base_price=Decimal("28.00"),
            tags="测试",
            status="available",
            stock=10,
        )
        self.p_cold_b = Product(
            sku=f"{self.PREFIX}-B",
            name=f"{self.PREFIX}冷萃B",
            category="冷萃",
            description="disambiguation test B",
            base_price=Decimal("29.00"),
            tags="测试",
            status="available",
            stock=10,
        )
        self.p_unique = Product(
            sku=f"{self.PREFIX}-C",
            name=f"{self.PREFIX}美式",
            category="咖啡",
            description="disambiguation test unique",
            base_price=Decimal("22.00"),
            tags="测试",
            status="available",
            stock=10,
        )
        for product in (self.p_cold_a, self.p_cold_b, self.p_unique):
            self.db.add(product)
        self.db.commit()
        for product in (self.p_cold_a, self.p_cold_b, self.p_unique):
            self.db.refresh(product)

    def tearDown(self):
        self.db.query(Product).filter(Product.sku.like(f"{self.PREFIX}-%")).delete(
            synchronize_session=False
        )
        self.db.commit()
        self.db.close()

    def test_exact_name_hits(self):
        product = get_product_by_name(self.db, f"{self.PREFIX}冷萃A")
        self.assertIsNotNone(product)
        self.assertEqual(product.product_id, self.p_cold_a.product_id)

    def test_unique_substring_tolerated(self):
        # Substring appears in exactly one product → accepted (colloquial ordering).
        product = get_product_by_name(self.db, f"{self.PREFIX}美式")
        self.assertIsNotNone(product)
        self.assertEqual(product.product_id, self.p_unique.product_id)

    def test_ambiguous_substring_raises_not_pick_cheapest(self):
        # Substring matches both cold-brew rows → must raise, not return A (cheaper).
        with self.assertRaises(AmbiguousProductError) as ctx:
            get_product_by_name(self.db, f"{self.PREFIX}冷萃")
        candidates = {c.name for c in ctx.exception.candidates}
        self.assertEqual(candidates, {self.p_cold_a.name, self.p_cold_b.name})

    def test_nonexistent_returns_none(self):
        self.assertIsNone(get_product_by_name(self.db, f"{self.PREFIX}不存在"))

    def test_empty_query_returns_none(self):
        self.assertIsNone(get_product_by_name(self.db, ""))

    def test_resolve_line_translates_ambiguity_to_order_error(self):
        with self.assertRaises(OrderError) as ctx:
            resolve_line(self.db, f"{self.PREFIX}冷萃")
        self.assertIn("匹配到多杯", str(ctx.exception))

    def test_resolve_line_exact_returns_line_spec(self):
        line = resolve_line(self.db, f"{self.PREFIX}美式")
        self.assertEqual(line.product.product_id, self.p_unique.product_id)
        self.assertEqual(line.unit_price, Decimal("22.00"))


if __name__ == "__main__":
    unittest.main()
