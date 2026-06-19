"""灌入《咖啡风味手册》示例段落 + 一个测试用户"""
from decimal import Decimal

from app.db.database import SessionLocal
from app.db.models import CoffeeKB, User

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


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(
                User(
                    user_id=1,
                    nickname="测试顾客",
                    balance=Decimal("100.00"),
                    taste_preference="不加糖",
                )
            )
            print("已创建测试用户 user_id=1，余额 100.00")
        if db.query(CoffeeKB).count() == 0:
            for item in SAMPLE_KB:
                db.add(CoffeeKB(**item))
            print(f"已灌入 {len(SAMPLE_KB)} 条咖啡知识")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
