"""幂等迁移脚本：创建 user_profile(用户画像) 表。

幂等：表已存在则跳过，不删数据，可重复运行。

    python scripts/migrate_user_profile.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_profile (
    profile_id   BIGINT NOT NULL AUTO_INCREMENT,
    user_id      BIGINT NOT NULL,
    summary      VARCHAR(200) NULL,
    profile_json TEXT NULL,
    last_msg_id  BIGINT NOT NULL DEFAULT 0,
    order_count  INT NOT NULL DEFAULT 0,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (profile_id),
    UNIQUE KEY uq_user_profile_user_id (user_id),
    CONSTRAINT fk_user_profile_user FOREIGN KEY (user_id) REFERENCES user (user_id),
    INDEX idx_user_profile_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def main() -> None:
    print("[migrate_user_profile] 开始迁移…")
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        print("[migrate_user_profile] 已确保 user_profile 表存在（幂等）。")
    print("[migrate_user_profile] 迁移完成。")


if __name__ == "__main__":
    main()
