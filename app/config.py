from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # OpenAI-compatible LLM provider.
    llm_api_key: str = ""
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


settings = Settings()
