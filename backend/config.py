from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # JWT
    jwt_secret: str = "change-this-secret-min-32-chars-long"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Twitter
    twitter_bearer_token: str = ""

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "invest-assistant"

    # CoinGecko
    coingecko_api_key: str = ""

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    # Monitor intervals (sekundy)
    twitter_poll_interval: int = 180   # 3 minuty
    news_poll_interval: int = 300      # 5 minut
    market_snapshot_interval: int = 3600  # 1 godzina

    # Relevance threshold - tylko powyżej wysyłamy alert
    event_relevance_threshold: float = 0.6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
