"""Seed users, wallets, the normalized product catalog, and (legacy) coffee_kb."""
from decimal import Decimal

from app.db.database import SessionLocal
from app.db.models import (
    CoffeeKB,
    Product,
    ProductOption,
    ProductOptionGroup,
    User,
)
from app.domain_constants import OPTION_SELECTION_SINGLE, WALLET_CURRENCY_CNY
from app.services import wallet_service

SAMPLE_KB = [
    {
        "coffee_name": "柑橘冷萃",
        "content": (
            "柑橘冷萃采用埃塞俄比亚耶加雪菲豆，低温冷萃18小时，带有明亮的柑橘、柠檬皮果香，"
            "口感清甜爽口，层次分明，是夏天最受欢迎的果香系咖啡。不加糖不加奶，纯饮最佳。"
        ),
        "price": Decimal("28.00"),
        "tags": "果香,柑橘,清甜,冷萃,无奶",
    },
    {
        "coffee_name": "莓果拿铁",
        "content": (
            "莓果拿铁以意式浓缩为基底，加入燕麦奶与莓果糖浆，融合出酸甜的莓果风味与丝滑奶香，"
            "适合喜欢浓郁口感的顾客。含有牛奶。"
        ),
        "price": Decimal("32.00"),
        "tags": "果香,莓果,牛奶,拿铁",
    },
    {
        "coffee_name": "焦糖玛奇朵",
        "content": (
            "焦糖玛奇朵在香浓牛奶与浓缩咖啡间淋上焦糖酱，甜润顺滑，焦糖香气浓郁，"
            "是经典的甜系咖啡。含有牛奶和糖。"
        ),
        "price": Decimal("30.00"),
        "tags": "甜,焦糖,牛奶,拿铁",
    },
    {
        "coffee_name": "美式咖啡",
        "content": (
            "美式咖啡由双份浓缩加热水制成，口感干净纯粹，微苦回甘，零糖零奶，热量极低，"
            "适合追求纯粹咖啡风味的顾客。"
        ),
        "price": Decimal("22.00"),
        "tags": "苦,纯粹,无奶,无糖,低热量",
    },
    {
        "coffee_name": "椰香冷萃",
        "content": (
            "椰香冷萃将冷萃咖啡与椰乳融合，带有清新的椰子香气与顺滑口感，微甜不腻，"
            "是乳糖不耐受人群的友好选择。不含牛奶。"
        ),
        "price": Decimal("29.00"),
        "tags": "椰香,清甜,冷萃,无牛奶",
    },
]


# Normalized catalog mirroring SAMPLE_KB. The first product (美式咖啡) carries a
# demo option group so order snapshotting + price-delta math is exercised.
SAMPLE_PRODUCTS = [
    {
        "sku": "AMERICANO",
        "name": "美式咖啡",
        "category": "咖啡",
        "description": SAMPLE_KB[3]["content"],
        "base_price": Decimal("22.00"),
        "tags": SAMPLE_KB[3]["tags"],
        "stock": 100,
    },
    {
        "sku": "CITRUS-COLD-BREW",
        "name": "柑橘冷萃",
        "category": "冷萃",
        "description": SAMPLE_KB[0]["content"],
        "base_price": Decimal("28.00"),
        "tags": SAMPLE_KB[0]["tags"],
        "stock": 50,
    },
    {
        "sku": "BERRY-LATTE",
        "name": "莓果拿铁",
        "category": "拿铁",
        "description": SAMPLE_KB[1]["content"],
        "base_price": Decimal("32.00"),
        "tags": SAMPLE_KB[1]["tags"],
        "stock": 50,
    },
    {
        "sku": "CARAMEL-MACCHIATO",
        "name": "焦糖玛奇朵",
        "category": "拿铁",
        "description": SAMPLE_KB[2]["content"],
        "base_price": Decimal("30.00"),
        "tags": SAMPLE_KB[2]["tags"],
        "stock": 50,
    },
    {
        "sku": "COCONUT-COLD-BREW",
        "name": "椰香冷萃",
        "category": "冷萃",
        "description": SAMPLE_KB[4]["content"],
        "base_price": Decimal("29.00"),
        "tags": SAMPLE_KB[4]["tags"],
        "stock": 50,
    },
]


def _seed_legacy_kb(db) -> None:
    if db.query(CoffeeKB).count() == 0:
        for item in SAMPLE_KB:
            db.add(CoffeeKB(**item))
        print(f"已灌入 {len(SAMPLE_KB)} 条 legacy coffee_kb 知识")


def _seed_products(db) -> None:
    if db.query(Product).count() > 0:
        return
    for spec in SAMPLE_PRODUCTS:
        db.add(Product(status="available", **spec))
    db.flush()

    americano = db.query(Product).filter(Product.sku == "AMERICANO").one()
    # 杯型规格组：中杯 / 大杯（+3）。
    size_group = ProductOptionGroup(
        product_id=americano.product_id,
        name="杯型",
        selection_type=OPTION_SELECTION_SINGLE,
        is_required=1,
        sort_order=1,
    )
    db.add(size_group)
    db.flush()
    db.add(ProductOption(group_id=size_group.group_id, name="中杯", price_delta=Decimal("0.00"), sort_order=1))
    db.add(ProductOption(group_id=size_group.group_id, name="大杯", price_delta=Decimal("3.00"), sort_order=2))

    # 奶类规格组（可选）。
    milk_group = ProductOptionGroup(
        product_id=americano.product_id,
        name="奶类",
        selection_type=OPTION_SELECTION_SINGLE,
        is_required=0,
        sort_order=2,
    )
    db.add(milk_group)
    db.flush()
    db.add(ProductOption(group_id=milk_group.group_id, name="不加奶", price_delta=Decimal("0.00"), sort_order=1))
    db.add(ProductOption(group_id=milk_group.group_id, name="燕麦奶", price_delta=Decimal("2.00"), sort_order=2))
    print(f"已灌入 {len(SAMPLE_PRODUCTS)} 个商品 + 美式咖啡规格组")


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    user_id=1,
                    nickname="测试顾客",
                    taste_preference="不加糖",
                )
            )
            db.flush()
            print("已创建测试用户 user_id=1")
        # CNY 钱包为权威余额。余额通过 append-only 流水 topup 写入，保证审计链完整。
        existing_topup = (
            db.query(wallet_service.BalanceTransaction)
            .filter(
                wallet_service.BalanceTransaction.user_id == 1,
                wallet_service.BalanceTransaction.currency == WALLET_CURRENCY_CNY,
                wallet_service.BalanceTransaction.type == "topup",
            )
            .first()
        )
        if existing_topup is None:
            wallet_service.topup(
                db,
                user_id=1,
                amount=Decimal("50.00"),
                note="种子充值",
            )
            db.commit()
            print("已为测试用户充值 ¥50.00 到 CNY 钱包")

        _seed_legacy_kb(db)
        _seed_products(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
