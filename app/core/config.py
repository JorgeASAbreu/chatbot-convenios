from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = ""
    app_env: str = "development"
    log_level: str = "INFO"
    llm_provider: Literal["none", "openai", "gemini"] = "none"
    openai_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_budget_usd: Decimal = Decimal("5.00")
    gemini_warn_threshold: Decimal = Decimal("0.80")
    gemini_cost_input_per_1m: Decimal = Decimal("0")
    gemini_cost_output_per_1m: Decimal = Decimal("0")
    streamlit_host: str = "0.0.0.0"
    streamlit_port: int = 8501
    dados_mg_proxy: str = ""
    admin_initial_user: str = "admin"
    admin_initial_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
