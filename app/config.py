from pathlib import Path
from decimal import Decimal
from typing import Literal
from urllib.parse import quote

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


_PLACEHOLDER_SECRETS = {
    "sk-your-key-here",
    "your-openai-api-key",
    "your-deepseek-api-key",
}

_PLACEHOLDER_AUTH_SECRETS = {
    "dev-only-change-me-in-prod",
    "change-me-to-a-random-long-string-in-production",
    "change-me-in-production",
}

_LOCAL_CORS_ORIGINS = (
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
)


def _clean_secret(value: str | None) -> str:
    return (value or "").strip()


def _is_real_secret(value: str | None) -> bool:
    text = _clean_secret(value)
    return bool(text) and text not in _PLACEHOLDER_SECRETS and not text.startswith("sk-your")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["local", "test", "production"] = "local"
    # Comma-separated explicit origins. Empty means local development defaults
    # in local/test and same-origin only (no CORS origins) in production.
    cors_allowed_origins: str = ""

    # DB_MODE(数据库模式)：决定数据存到哪里。sqlite=本地文件运行，mysql=远程服务器。
    # 默认 sqlite(本地文件数据库)，本地开发零配置即可跑。
    db_mode: Literal["sqlite", "mysql"] = "sqlite"
    sqlite_path: str = "coffee_ai.db"
    sqlite_busy_timeout_ms: int = 5000

    # MySQL 连接信息（仅 DB_MODE=mysql 时使用）。
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "coffee"
    mysql_password: str = ""
    mysql_database: str = "coffee_ai"

    # USE_FAKEREDIS(启用模拟Redis)：true=进程内模拟，无需安装 Redis 服务。
    # 默认 true(本地零配置)，设为 false 则连接真实 Redis 服务器。
    use_fakeredis: bool = True
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    # Redis socket 超时（秒）:建连 / 读写命令;超时即降级,避免 /chat 挂死等约 1 分钟
    redis_socket_connect_timeout: float = 3.0
    redis_socket_timeout: float = 5.0

    # OpenAI-compatible LLM provider.
    llm_api_key: str = ""
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    # LLM(大模型) 单次 HTTP(超文本传输) 请求超时秒数；过期会走 mock(降级) 兜底
    llm_timeout_seconds: float = 15.0
    # LLM 分阶段超时（秒）:连接 / 意图推断 / 生成 / 复盘;细分以避免单个环节长时间阻塞
    llm_connect_timeout_seconds: float = 10.0
    llm_intent_timeout_seconds: float = 4.0
    llm_generation_timeout_seconds: float = 40.0
    llm_review_timeout_seconds: float = 6.0

    # Chat memory.
    chat_history_rounds: int = 5
    chat_history_ttl: int = 1800

    # Real-time visualization fan-out.
    visualization_redis_channel: str = "coffee:visualization:events"
    visualization_connection_queue_size: int = 100
    visualization_send_timeout_ms: int = 500
    visualization_presence_ttl_seconds: int = 45
    visualization_skill_sweep_lock_ttl_seconds: int = 75

    # Autonomous digital customer agent.
    autonomous_agent_enabled: bool = True
    autonomous_agent_interval_min_seconds: float = 45.0
    autonomous_agent_interval_max_seconds: float = 75.0
    autonomous_agent_step_interval_seconds: float = 4.0
    autonomous_agent_status_ttl_seconds: int = 180

    # A2A Skill / EvoMap credit ordering.
    skill_free_order_limit: int = 2
    evomap_payment_mode: str = "service_order"
    evomap_hub_url: str = "https://evomap.ai"
    evomap_service_listing_id: str = ""
    evomap_order_credits: int = 1
    evomap_request_timeout_seconds: float = 15.0
    skill_payment_processing_timeout_seconds: int = 120
    skill_reconcile_enabled: bool = True
    skill_reconcile_interval_seconds: int = 60
    skill_reconcile_batch_size: int = 10
    skill_reconcile_claim_timeout_seconds: int = 300
    evomap_credit_rate: str = "1"
    evomap_atp_caps: str = "a2a_super_order,coffee_order"

    # EvoMap node identity（群体进化：发布教训 + 拉取社区经验）
    evomap_node_id: str = ""
    evomap_node_secret: str = ""
    evomap_guild_id: str = ""

    # Auth session cookie signing (for the new account login). Set a strong
    # random value in .env; a dev default keeps local runs working.
    auth_secret_key: str = "dev-only-change-me-in-prod"
    auth_cookie_name: str = "coffee_session"
    auth_cookie_max_age_seconds: int = 7 * 24 * 3600
    auth_cookie_secure: bool = False
    admin_bootstrap_username: str = ""
    registration_bonus_cny: Decimal = Decimal("50.00")
    allow_registration_bonus_in_production: bool = False

    @field_validator("environment", mode="before")
    @classmethod
    def _validate_environment(cls, value: object) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"local", "test", "production"}:
            raise ValueError("ENVIRONMENT must be 'local', 'test', or 'production'")
        return normalized

    @field_validator("db_mode", mode="before")
    @classmethod
    def _validate_db_mode(cls, value: object) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"sqlite", "mysql"}:
            raise ValueError("DB_MODE must be either 'sqlite' or 'mysql'")
        return normalized

    @field_validator("sqlite_busy_timeout_ms")
    @classmethod
    def _validate_sqlite_busy_timeout(cls, value: int) -> int:
        if value < 0:
            raise ValueError("SQLITE_BUSY_TIMEOUT_MS must be non-negative")
        return value

    @field_validator("skill_payment_processing_timeout_seconds")
    @classmethod
    def _validate_skill_payment_processing_timeout(cls, value: int) -> int:
        if value < 30:
            raise ValueError("SKILL_PAYMENT_PROCESSING_TIMEOUT_SECONDS must be at least 30")
        return value

    @field_validator("skill_reconcile_interval_seconds")
    @classmethod
    def _validate_skill_reconcile_interval(cls, value: int) -> int:
        if value < 10:
            raise ValueError("SKILL_RECONCILE_INTERVAL_SECONDS must be at least 10")
        return value

    @field_validator("skill_reconcile_batch_size")
    @classmethod
    def _validate_skill_reconcile_batch(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("SKILL_RECONCILE_BATCH_SIZE must be between 1 and 100")
        return value

    @field_validator("skill_reconcile_claim_timeout_seconds")
    @classmethod
    def _validate_skill_reconcile_timeout(cls, value: int) -> int:
        if value < 60:
            raise ValueError("SKILL_RECONCILE_CLAIM_TIMEOUT_SECONDS must be at least 60")
        return value

    @field_validator("registration_bonus_cny")
    @classmethod
    def _validate_registration_bonus(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("REGISTRATION_BONUS_CNY must be non-negative")
        return value.quantize(Decimal("0.01"))

    @model_validator(mode="after")
    def _validate_production_security(self) -> "Settings":
        if self.environment != "production":
            return self
        if (
            self.auth_secret_key.strip().lower() in _PLACEHOLDER_AUTH_SECRETS
            or len(self.auth_secret_key.strip()) < 32
        ):
            raise ValueError(
                "Production requires a non-default AUTH_SECRET_KEY of at least 32 characters"
            )
        if not self.auth_cookie_secure:
            raise ValueError("Production requires AUTH_COOKIE_SECURE=true")
        if (
            self.registration_bonus_cny > 0
            and not self.allow_registration_bonus_in_production
        ):
            raise ValueError(
                "Production registration bonus is disabled by default; set "
                "REGISTRATION_BONUS_CNY=0 or explicitly opt in"
            )
        if "*" in self.cors_allowed_origin_list:
            raise ValueError("Production CORS_ALLOWED_ORIGINS must not contain '*'")
        return self

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        raw = [origin.strip() for origin in self.cors_allowed_origins.split(",")]
        configured = [origin for origin in raw if origin]
        if not configured and self.environment in {"local", "test"}:
            configured = list(_LOCAL_CORS_ORIGINS)
        return list(dict.fromkeys(configured))

    @property
    def database_url(self) -> URL:
        if self.db_mode == "sqlite":
            sqlite_path = self.sqlite_path.strip()
            if not sqlite_path:
                raise ValueError("SQLITE_PATH must not be empty")
            database = ":memory:" if sqlite_path == ":memory:" else str(Path(sqlite_path).expanduser())
            return URL.create("sqlite+pysqlite", database=database)
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )

    @property
    def redis_url(self) -> str:
        auth = f":{quote(self.redis_password, safe='')}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def effective_llm_api_key(self) -> str:
        for value in (self.llm_api_key, self.deepseek_api_key, self.openai_api_key):
            if _is_real_secret(value):
                return _clean_secret(value)
        return ""

    @property
    def llm_api_key_source(self) -> str | None:
        candidates = (
            ("LLM_API_KEY", self.llm_api_key),
            ("DEEPSEEK_API_KEY", self.deepseek_api_key),
            ("OPENAI_API_KEY", self.openai_api_key),
        )
        for name, value in candidates:
            if _is_real_secret(value):
                return name
        return None

    @property
    def llm_status_reason(self) -> str:
        if self.llm_api_key_source:
            return "configured"
        configured_placeholders = [
            name
            for name, value in (
                ("LLM_API_KEY", self.llm_api_key),
                ("DEEPSEEK_API_KEY", self.deepseek_api_key),
                ("OPENAI_API_KEY", self.openai_api_key),
            )
            if _clean_secret(value)
        ]
        if configured_placeholders:
            return "placeholder_or_invalid_api_key"
        return "missing_api_key"


settings = Settings()
