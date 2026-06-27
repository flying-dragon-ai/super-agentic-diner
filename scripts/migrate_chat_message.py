"""幂等迁移脚本：创建 chat_message(对话归档) 表。

幂等：表已存在则跳过，不删数据，可重复运行。

    python scripts/migrate_chat_message.py

SQLite(本地文件数据库) 由 Base.metadata.create_all() 自动建表；本脚本主要面向 MySQL(关系型数据库)，
用原生 DDL(数据定义语言) 兼容两种后端（IF NOT EXISTS 语义两边都支持）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS chat_message (
    message_id  BIGINT NOT NULL AUTO_INCREMENT,
    user_id     BIGINT NOT NULL,
    role        VARCHAR(16) NOT NULL,
    content     TEXT NOT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (message_id),
    CONSTRAINT fk_chat_msg_user FOREIGN KEY (user_id) REFERENCES user (user_id),
    INDEX idx_chat_msg_user_id (user_id, message_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def main() -> None:
    print("[migrate_chat_message] 开始迁移…")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        print("[migrate_chat_message] 已确保 chat_message 表存在（幂等）。")
    print("[migrate_chat_message] 迁移完成。")


if __name__ == "__main__":
    main()
