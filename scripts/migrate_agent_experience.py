"""幂等迁移脚本：创建 agent_experience(经验存储) 表。

幂等：表已存在则跳过，不删数据，可重复运行。

    python scripts/migrate_agent_experience.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import engine  # noqa: E402


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS agent_experience (
    experience_id BIGINT NOT NULL AUTO_INCREMENT,
    user_id       BIGINT NOT NULL,
    agent_role    VARCHAR(32) NOT NULL,
    coffee_name   VARCHAR(128) NULL,
    context_tags  VARCHAR(255) NULL,
    insight       TEXT NOT NULL,
    rating        INT NULL,
    order_id      BIGINT NULL,
    correlation_id VARCHAR(128) NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (experience_id),
    INDEX idx_agent_exp_user_tags (user_id, context_tags),
    INDEX idx_agent_exp_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def main() -> None:
    print("[migrate_agent_experience] 开始迁移…")
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'agent_experience'"
            )
        ).scalar()
        if exists:
            print("[migrate_agent_experience] 表 agent_experience 已存在，跳过。")
            return
        conn.execute(text(CREATE_TABLE_SQL))
        print("[migrate_agent_experience] 已创建 agent_experience 表。")
    print("[migrate_agent_experience] 迁移完成。")


if __name__ == "__main__":
    main()
