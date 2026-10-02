from sqlalchemy.orm import Session

from app.core.config import Settings
from app.llm.providers import GeminiProvider, NoneProvider, OpenAIProvider


def provider(settings: Settings, db: Session | None = None, user_id: int | None = None):
    return (
        {"none": NoneProvider, "openai": OpenAIProvider, "gemini": GeminiProvider}[
            settings.llm_provider
        ](settings, db, user_id)
        if settings.llm_provider != "none"
        else NoneProvider()
    )
