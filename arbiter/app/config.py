from pydantic_settings import BaseSettings, SettingsConfigDict


class ArbiterSettings(BaseSettings):
    node_id: str = "C"
    host: str = "0.0.0.0"
    port: int = 9000

    arbiter_db_path: str = "data/arbiter.db"

    server_a_url: str = "http://192.168.111.128:8000"
    server_b_url: str = "http://192.168.111.129:8000"

    lease_ttl_ms: int = 3000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = ArbiterSettings()