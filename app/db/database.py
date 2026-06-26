from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

if settings.db_mode == "sqlite":
    # SQLite(本地文件数据库)：不需要连接池参数；
    # check_same_thread=False 让 FastAPI(异步框架) 多线程共享同一连接。
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    # MySQL：连接池保活（pool_pre_ping 防断连，pool_recycle 定期回收）。
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
