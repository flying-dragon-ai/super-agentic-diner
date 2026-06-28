"""Seed users, wallets, the normalized product catalog, and (legacy) coffee_kb."""
from decimal import Decimal

from app.db.database import SessionLocal
from app.db.models import (
    CoffeeKB,
    Product,
    ProductOption,
    ProductOptionGroup,
    User,
    UserAccount,
)
from app.domain_constants import IDENTITY_STATUS_ACTIVE, OPTION_SELECTION_SINGLE, WALLET_CURRENCY_CNY
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
    # ===== 热饮系列 =====
    {
        "sku": "HOT-LATTE",
        "name": "经典热拿铁",
        "category": "热饮",
        "description": (
            "经典热拿铁以醇厚意式浓缩为基底，注入温热燕麦奶，拉花细腻。"
            "口感丝滑顺口，奶香与咖啡完美平衡，是冬日暖身的经典选择。"
        ),
        "base_price": Decimal("26.00"),
        "tags": "热饮,拿铁,燕麦奶,丝滑",
        "stock": 80,
    },
    {
        "sku": "HOT-MOCHA",
        "name": "热摩卡",
        "category": "热饮",
        "description": (
            "热摩卡将浓缩咖啡与比利时巧克力融合，加热牛奶与奶油顶，"
            "浓郁可可香与咖啡苦甜交织，是巧克力爱好者的冬日首选。"
        ),
        "base_price": Decimal("30.00"),
        "tags": "热饮,摩卡,巧克力,浓郁",
        "stock": 60,
    },
    {
        "sku": "HOT-CAPPUCCINO",
        "name": "卡布奇诺",
        "category": "热饮",
        "description": (
            "经典意式卡布奇诺，浓缩咖啡搭配等量热牛奶与绵密奶泡，"
            "层次分明，口感丰富，是传统咖啡爱好者的不二之选。"
        ),
        "base_price": Decimal("25.00"),
        "tags": "热饮,卡布奇诺,奶泡,经典",
        "stock": 70,
    },
    {
        "sku": "HOT-AMERICANO",
        "name": "热美式",
        "category": "热饮",
        "description": (
            "热美式由双份浓缩咖啡注入热水，保留咖啡原有风味，"
            "干净纯粹，微苦回甘，零糖零奶。适合追求纯粹咖啡体验的顾客。"
        ),
        "base_price": Decimal("20.00"),
        "tags": "热饮,美式,纯粹,无奶",
        "stock": 100,
    },
    # ===== 冷饮系列 =====
    {
        "sku": "ICE-AMERICANO",
        "name": "冰美式",
        "category": "冷饮",
        "description": (
            "冰美式以双份浓缩咖啡浇在冰块上，清爽透亮，保留咖啡的醇苦本色。"
            "夏日提神首选，零糖零卡。"
        ),
        "base_price": Decimal("22.00"),
        "tags": "冷饮,美式,冰,清爽,无奶",
        "stock": 90,
    },
    {
        "sku": "ICE-LATTE",
        "name": "冰拿铁",
        "category": "冷饮",
        "description": (
            "冰拿铁将浓缩咖啡缓缓注入冰牛奶，形成美丽的渐变层次。"
            "口感丝滑清凉，奶香怡人，是夏日最受欢迎的经典冰咖啡。"
        ),
        "base_price": Decimal("26.00"),
        "tags": "冷饮,拿铁,冰,牛奶",
        "stock": 80,
    },
    {
        "sku": "SPARKLING-WATER",
        "name": "西西里气泡水",
        "category": "冷饮",
        "description": (
            "西西里气泡水以新鲜柠檬汁搭配苏打水与薄荷叶，"
            "气泡绵密，酸甜解渴，不含咖啡因。适合想要清爽无咖啡因饮品的顾客。"
        ),
        "base_price": Decimal("18.00"),
        "tags": "冷饮,气泡水,柠檬,无咖啡因,清爽",
        "stock": 60,
    },
    # ===== 季节性特调 =====
    {
        "sku": "SUMMER-MANGO",
        "name": "夏日芒芒特调",
        "category": "特调",
        "description": (
            "夏日芒芒特调将新鲜芒果泥与冷萃咖啡融合，顶部铺满芝士奶盖。"
            "果香浓郁，层次丰富，是夏季限定的人气特调饮品。"
        ),
        "base_price": Decimal("35.00"),
        "tags": "特调,芒果,冷萃,奶盖,夏季限定",
        "stock": 30,
    },
    {
        "sku": "AUTUMN-CINNAMON",
        "name": "秋日肉桂拿铁",
        "category": "特调",
        "description": (
            "秋日肉桂拿铁在经典拿铁基础上加入肉桂粉与焦糖酱，"
            "温暖香气扑面，口感丰富层次分明，是秋季限定暖心特调。"
        ),
        "base_price": Decimal("33.00"),
        "tags": "特调,肉桂,拿铁,秋季限定,热饮",
        "stock": 25,
    },
]


def _seed_legacy_kb(db) -> None:
    if db.query(CoffeeKB).count() == 0:
        for item in SAMPLE_KB:
            db.add(CoffeeKB(**item))
        print(f"已灌入 {len(SAMPLE_KB)} 条 legacy coffee_kb 知识")


def _seed_products(db) -> None:
    # Idempotent upsert: only add products whose SKU doesn't already exist.
    existing_skus = {sku for (sku,) in db.query(Product.sku).all()}
    new_count = 0
    for spec in SAMPLE_PRODUCTS:
        if spec["sku"] in existing_skus:
            continue
        db.add(Product(status="available", **spec))
        new_count += 1
    db.flush()

    americano = db.query(Product).filter(Product.sku == "AMERICANO").one()
    # Skip option group creation if it already exists (idempotent).
    existing_groups = db.query(ProductOptionGroup).filter(ProductOptionGroup.product_id == americano.product_id).count()
    if existing_groups > 0:
        return
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
    print(f"已同步 {len(SAMPLE_PRODUCTS)} 个商品（新增 {new_count}），美式咖啡规格组已就绪")


def _seed_default_account(db) -> None:
    """创建默认登录账号（首次初始化用，已存在则跳过）。"""
    if db.query(UserAccount).count() > 0:
        return
    import bcrypt
    account = UserAccount(
        username="admin",
        password_hash=bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("ascii"),
        nickname="管理员",
        user_id=1,
        status=IDENTITY_STATUS_ACTIVE,
    )
    db.add(account)
    print("已创建默认账号 admin / admin123")


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
            print("已为测试用户充值 50.00 CNY 到钱包")

        _seed_legacy_kb(db)
        _seed_products(db)
        _seed_default_account(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
