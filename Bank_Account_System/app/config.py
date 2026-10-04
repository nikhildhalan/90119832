from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_name: str = 'bank-account-service'
    app_zone: str = 'Asia/Kolkata'
    database_url: str = 'postgresql://bank_app:bank_app_pwd@localhost:5433/bankdb'
    redis_url: str = 'redis://localhost:6379/0'
    kafka_bootstrap_servers: str = 'localhost:9092'
    account_cache_ttl: int = 600
    statement_cache_ttl: int = 300
    idempotency_ttl: int = 86400
    kafka_timeout_seconds: float = 4.0
    app_host: str = '0.0.0.0'
    app_port: int = 8080

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
