from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    node_id: str = "A"
    host: str = "0.0.0.0"
    port: int = 8000
    max_clients: int = 20

    db_path: str = "data/bank.db"
    log_path: str = "logs/server.jsonl"

    server_a_url: str = "http://192.168.56.11:8000"
    server_b_url: str = "http://192.168.56.12:8000"
    arbiter_url: str = "http://192.168.56.13:9000"

    lease_ttl_ms: int = 3000
    heartbeat_interval_ms: int = 500

    enable_fault_injection: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()