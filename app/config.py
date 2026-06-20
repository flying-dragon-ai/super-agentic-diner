from pydantic_settings import BaseSettings, SettingsConfigDict


_PLACEHOLDER_SECRETS = {
    "sk-your-key-here",
    "your-openai-api-key",
    "your-deepseek-api-key",
}


def _clean_secret(value: str | None) -> str:
    return (value or "").strip()


def _is_real_secret(value: str | None) -> bool:
    text = _clean_secret(value)
    return bool(text) and text not in _PLACEHOLDER_SECRETS and not text.startswith("sk-your")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MySQL is the only supported persistent database.
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "coffee"
    mysql_password: str = "coffee123"
    mysql_database: str = "coffee_ai"

    # Redis is the only supported memory/middleware backend.
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    # Socket timeouts so a flaky/unreachable Redis fails fast instead of
    # hanging the request. The redis-py default is no limit, which produced
    # ~56s hangs and 500s on /chat when the network to the cloud Redis dipped.
    redis_socket_connect_timeout: float = 2.0
    redis_socket_timeout: float = 3.0

    # OpenAI-compatible LLM provider.
    llm_api_key: str = ""
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Chat memory.
    chat_history_rounds: int = 5
    chat_history_ttl: int = 1800

    # A2A Skill / EvoMap credit ordering.
    skill_free_order_limit: int = 2
    evomap_payment_mode: str = "service_order"
    evomap_hub_url: str = "https://evomap.ai"
    evomap_service_listing_id: str = ""
    evomap_order_credits: int = 1
    evomap_request_timeout_seconds: float = 15.0
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

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
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
