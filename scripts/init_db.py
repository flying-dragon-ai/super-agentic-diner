"""建表 + 灌种子数据

用法：
    python scripts/init_db.py
"""
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，方便直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import models  # noqa: F401  触发模型注册
from app.db.database import Base, engine
from app.db.seed import seed


def main():
    print("创建数据表 ...")
    Base.metadata.create_all(engine)
    print("灌入种子数据 ...")
    seed()
    print("完成！启动服务：uvicorn app.main:app --reload")


if __name__ == "__main__":
    main()
