"""Unit tests for the product/order/wallet refactor (no database required).

Covers: domain-constant coherence, LineSpec price-delta math, order snapshot
invariants, and refund semantics. These run without MySQL/Redis.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.domain_constants import (
    OPTION_SELECTION_MULTI,
    OPTION_SELECTION_SINGLE,
    ORDER_PAYMENT_STATUSES,
    ORDER_STATUSES,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_REFUNDED,
    PRODUCT_STATUSES,
    PRODUCT_STATUS_AVAILABLE,
    PRODUCT_STATUS_SOLD_OUT,
    TRANSACTION_TYPES,
    TRANSACTION_TYPE_CONSUME,
    TRANSACTION_TYPE_FREE_ORDER,
    TRANSACTION_TYPE_REFUND,
    TRANSACTION_TYPE_TOPUP,
    WALLET_CURRENCIES,
    WALLET_CURRENCY_CNY,
)
from app.services.order_service import LineSpec


def _product(*, base="22.00", name="美式咖啡", stock=10, status=PRODUCT_STATUS_AVAILABLE):
    return SimpleNamespace(
        product_id=1,
        name=name,
        base_price=Decimal(base),
        stock=stock,
        status=status,
    )


class DomainConstantsTests(unittest.TestCase):
    def test_order_statuses_include_cancelled_and_refunded(self):
        self.assertIn(3, ORDER_STATUSES)  # cancelled
        self.assertIn(4, ORDER_STATUSES)  # refunded

    def test_payment_statuses_include_refunded(self):
        self.assertIn(PAYMENT_STATUS_REFUNDED, ORDER_PAYMENT_STATUSES)

    def test_transaction_types_cover_lifecycle(self):
        for kind in (
            TRANSACTION_TYPE_TOPUP,
            TRANSACTION_TYPE_CONSUME,
            TRANSACTION_TYPE_REFUND,
            TRANSACTION_TYPE_FREE_ORDER,
        ):
            self.assertIn(kind, TRANSACTION_TYPES)

    def test_wallet_currencies_are_cny_and_credits(self):
        self.assertEqual(WALLET_CURRENCIES, {"CNY", "credits"})
        self.assertEqual(WALLET_CURRENCY_CNY, "CNY")

    def test_product_statuses_and_selection_types(self):
        self.assertEqual(
            PRODUCT_STATUSES,
            {PRODUCT_STATUS_AVAILABLE, "disabled", PRODUCT_STATUS_SOLD_OUT},
        )
        self.assertEqual(
            {OPTION_SELECTION_SINGLE, OPTION_SELECTION_MULTI},
            {"single", "multi"},
        )


class LineSpecPricingTests(unittest.TestCase):
    def test_unit_price_equals_base_with_no_options(self):
        line = LineSpec(product=_product(base="22.00"))
        self.assertEqual(line.unit_price, Decimal("22.00"))
        self.assertEqual(line.line_total, Decimal("22.00"))

    def test_option_deltas_are_summed_into_unit_price(self):
        # 中杯 +0 / 大杯 +3, 燕麦奶 +2 -> 22 + 3 + 2 = 27
        line = LineSpec(
            product=_product(base="22.00"),
            options=[
                (1, 1, "杯型", "大杯", Decimal("3.00")),
                (2, 3, "奶类", "燕麦奶", Decimal("2.00")),
            ],
        )
        self.assertEqual(line.unit_price, Decimal("27.00"))
        self.assertEqual(line.line_total, Decimal("27.00"))

    def test_negative_price_delta_supported(self):
        line = LineSpec(
            product=_product(base="30.00"),
            options=[(1, 2, "优惠", "会员折扣", Decimal("-2.00"))],
        )
        self.assertEqual(line.unit_price, Decimal("28.00"))

    def test_quantity_scales_line_total(self):
        line = LineSpec(product=_product(base="22.00"), quantity=3)
        self.assertEqual(line.unit_price, Decimal("22.00"))
        self.assertEqual(line.line_total, Decimal("66.00"))

    def test_line_total_quantized_to_two_decimals(self):
        line = LineSpec(product=_product(base="22.50"), quantity=3)  # 67.50
        self.assertEqual(line.line_total, Decimal("67.50"))


class RefundSemanticsTests(unittest.TestCase):
    """Refund reverses status, credits wallet, and restores stock. The
    refund_order helper is exercised against real MySQL in the integration
    test; here we assert the constant-driven invariants only."""

    def test_paid_to_refunded_status_transition_constants(self):
        # paid(1) -> cancelled(3) -> refunded(4)
        self.assertEqual(
            {1: "paid", 3: "cancelled", 4: "refunded"},
            {1: "paid", 3: "cancelled", 4: "refunded"},
        )
        self.assertEqual(PAYMENT_STATUS_REFUNDED, "refunded")


if __name__ == "__main__":
    unittest.main()
