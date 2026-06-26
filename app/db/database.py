from sqlalchemy import create_engine, event
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

    # WAL(预写日志) 模式 + 性能 PRAGMA(编译指示)：
    # WAL 允许并发读不阻塞写，synchronous=NORMAL 平衡安全与速度，
    # cache_size 负值=KB（-65536=64MB 缓存），减少磁盘 I/O。
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-65536")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()
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
