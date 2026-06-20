"""Integration tests against the configured MySQL for the catalog/order/wallet
refactor. Skipped automatically when MySQL is not reachable.

Covers:
- migration scripts are idempotent (re-run is a no-op for inserts)
- place_orders writes header + order_item + consume txn + stock decrement
- refund_order restores stock + wallet and sets refunded status
- ledger chain balances: SUM(txn) == wallet balance
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from decimal import Decimal

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import (
    BalanceTransaction,
    Order,
    OrderItem,
    OrderItemOption,
    Product,
    User,
    UserWallet,
)
from app.domain_constants import (
    ORDER_STATUS_REFUNDED,
    PAYMENT_STATUS_REFUNDED,
    TRANSACTION_TYPE_CONSUME,
    TRANSACTION_TYPE_REFUND,
    WALLET_CURRENCY_CNY,
)
from app.services import order_service, wallet_service


def _mysql_reachable() -> bool:
    try:
        import pymysql

        pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            connect_timeout=5,
        ).close()
        return True
    except Exception:
        return False


@unittest.skipUnless(_mysql_reachable(), "MySQL not reachable")
class MysqlRefactorIntegrationTests(unittest.TestCase):
    """Runs against the real configured MySQL; each test owns + cleans its data."""

    TEST_SKU = "TEST-INTEGRATION-LATTE"
    TEST_NAME = "测试集成拿铁"
    TEST_USER_NICK = "test-integration-user"

    def setUp(self):
        self.db = SessionLocal()
        # Purge any leftover rows from an interrupted previous run, then seed fresh.
        self._purge_test_data()
        self.product = Product(
            sku=self.TEST_SKU,
            name=self.TEST_NAME,
            category="拿铁",
            description="integration test product",
            base_price=Decimal("20.00"),
            tags="测试",
            status="available",
            stock=5,
        )
        self.db.add(self.product)
        self.user = User(nickname=self.TEST_USER_NICK)
        self.db.add(self.user)
        self.db.flush()
        self.user_id = self.user.user_id
        wallet_service.topup(
            self.db,
            user_id=self.user_id,
            amount=Decimal("100.00"),
            note="integration test topup",
        )
        self.db.commit()
        self._created_order_ids: list[int] = []

    def tearDown(self):
        try:
            self._purge_test_data()
        finally:
            self.db.close()

    def _purge_test_data(self) -> None:
        """Remove every row owned by the test user + test product (idempotent)."""
        users = (
            self.db.query(User)
            .filter(User.nickname == self.TEST_USER_NICK)
            .all()
        )
        for orphan in users:
            uid = orphan.user_id
            order_ids = [
                o.order_id
                for o in self.db.query(Order).filter(Order.user_id == uid).all()
            ]
            for order_id in order_ids:
                item_ids = [
                    i.item_id
                    for i in self.db.query(OrderItem)
                    .filter(OrderItem.order_id == order_id)
                    .all()
                ]
                if item_ids:
                    self.db.query(OrderItemOption).filter(
                        OrderItemOption.item_id.in_(item_ids)
                    ).delete(synchronize_session=False)
                self.db.query(OrderItem).filter(
                    OrderItem.order_id == order_id
                ).delete(synchronize_session=False)
            self.db.query(BalanceTransaction).filter(
                BalanceTransaction.user_id == uid
            ).delete(synchronize_session=False)
            self.db.query(Order).filter(Order.user_id == uid).delete(
                synchronize_session=False
            )
            self.db.query(UserWallet).filter(UserWallet.user_id == uid).delete(
                synchronize_session=False
            )
            self.db.delete(orphan)
        self.db.query(Product).filter(Product.sku == self.TEST_SKU).delete(
            synchronize_session=False
        )
        self.db.commit()

    def test_place_orders_writes_header_items_wallet_and_stock(self):
        bal_before = wallet_service.get_balance(self.db, self.user_id, WALLET_CURRENCY_CNY)
        orders = order_service.place_orders(
            self.db,
            user_id=self.user_id,
            items=[(self.TEST_NAME, "integration-place-req-1")],
            source_type="web_dialog",
            payment_status="paid",
            correlation_id="integration-place",
        )
        order = orders[0]
        self._created_order_ids.append(order.order_id)

        self.assertEqual(order.total_amount, Decimal("20.00"))
        items = self.db.query(OrderItem).filter(OrderItem.order_id == order.order_id).all()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].product_name_snapshot, self.TEST_NAME)
        self.assertEqual(items[0].unit_price, Decimal("20.00"))
        self.assertEqual(items[0].line_total, Decimal("20.00"))
        self.db.refresh(self.product)
        self.assertEqual(self.product.stock, 4)
        bal_after = wallet_service.get_balance(self.db, self.user_id, WALLET_CURRENCY_CNY)
        self.assertEqual(bal_after, bal_before - Decimal("20.00"))
        txn = (
            self.db.query(BalanceTransaction)
            .filter(
                BalanceTransaction.order_id == order.order_id,
                BalanceTransaction.type == TRANSACTION_TYPE_CONSUME,
            )
            .first()
        )
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, Decimal("-20.0000"))
        self.assertEqual(Decimal(txn.balance_after), bal_after)

    def test_refund_restores_stock_wallet_and_sets_refunded_status(self):
        orders = order_service.place_orders(
            self.db,
            user_id=self.user_id,
            items=[(self.TEST_NAME, "integration-refund-req-1")],
            source_type="web_dialog",
            payment_status="paid",
            correlation_id="integration-refund",
        )
        order = orders[0]
        self._created_order_ids.append(order.order_id)

        refunded = order_service.refund_order(self.db, order.order_id)
        self.assertEqual(refunded.status, ORDER_STATUS_REFUNDED)
        self.assertEqual(refunded.payment_status, PAYMENT_STATUS_REFUNDED)
        self.assertIsNotNone(refunded.refunded_at)

        self.db.refresh(self.product)
        self.assertEqual(self.product.stock, 5)
        bal_after_refund = wallet_service.get_balance(
            self.db, self.user_id, WALLET_CURRENCY_CNY
        )
        self.assertEqual(bal_after_refund, Decimal("100.0000"))
        refund_txn = (
            self.db.query(BalanceTransaction)
            .filter(
                BalanceTransaction.order_id == order.order_id,
                BalanceTransaction.type == TRANSACTION_TYPE_REFUND,
            )
            .first()
        )
        self.assertIsNotNone(refund_txn)
        self.assertEqual(refund_txn.amount, Decimal("20.0000"))

    def test_ledger_chain_balances_for_wallet(self):
        """SUM(amount) over the wallet's transactions == wallet balance."""
        wallet = (
            self.db.query(UserWallet)
            .filter(
                UserWallet.user_id == self.user_id,
                UserWallet.currency == WALLET_CURRENCY_CNY,
            )
            .first()
        )
        total = sum(
            (
                Decimal(t.amount)
                for t in self.db.query(BalanceTransaction)
                .filter(
                    BalanceTransaction.user_id == self.user_id,
                    BalanceTransaction.currency == WALLET_CURRENCY_CNY,
                )
                .all()
            ),
            Decimal("0"),
        )
        self.assertEqual(Decimal(total), Decimal(wallet.balance))


@unittest.skipUnless(_mysql_reachable(), "MySQL not reachable")
class MigrationIdempotencyTests(unittest.TestCase):
    """Re-running each migration must not duplicate rows or fail."""

    def _run(self, module: str) -> int:
        return subprocess.call(
            [sys.executable, f"scripts/{module}.py"],
            env={**os.environ, "PYTHONPATH": "."},
        )

    def test_product_catalog_idempotent(self):
        self.assertEqual(self._run("migrate_product_catalog"), 0)
        self.assertEqual(self._run("migrate_product_catalog"), 0)

    def test_order_lineitem_idempotent(self):
        self.assertEqual(self._run("migrate_order_lineitem"), 0)
        self.assertEqual(self._run("migrate_order_lineitem"), 0)

    def test_wallet_ledger_idempotent(self):
        self.assertEqual(self._run("migrate_wallet_ledger"), 0)
        self.assertEqual(self._run("migrate_wallet_ledger"), 0)


if __name__ == "__main__":
    unittest.main()
