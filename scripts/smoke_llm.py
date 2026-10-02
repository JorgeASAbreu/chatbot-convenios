"""Chamada mínima e opcional ao provedor configurado; execução manual apenas."""

from app.core.config import get_settings


def main() -> int:
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "gemini":
        if not settings.gemini_enabled or not settings.gemini_api_key or not settings.gemini_model:
            print("Configure GEMINI_ENABLED, GEMINI_API_KEY e GEMINI_MODEL no .env.")
            return 2
        from google import genai

        print(f"provider={provider} model={settings.gemini_model}")
        try:
            response = genai.Client(api_key=settings.gemini_api_key).models.generate_content(
                model=settings.gemini_model, contents="Responda apenas OK."
            )
            usage = getattr(response, "usage_metadata", None)
            print(f"resultado={getattr(response, 'text', '')}")
            print(
                "usage input_tokens={} output_tokens={}".format(
                    getattr(usage, "prompt_token_count", None),
                    getattr(usage, "candidates_token_count", None),
                )
            )
            return 0
        except Exception as exc:
            print(f"Falha na chamada: {type(exc).__name__}")
            return 1
    if provider == "openai":
        if not settings.openai_enabled or not settings.openai_api_key or not settings.openai_model:
            print("Configure OPENAI_ENABLED, OPENAI_API_KEY e OPENAI_MODEL no .env.")
            return 2
        from openai import OpenAI

        print(f"provider={provider} model={settings.openai_model}")
        try:
            response = OpenAI(api_key=settings.openai_api_key, max_retries=0).responses.create(
                model=settings.openai_model, input="Responda apenas OK."
            )
            print(f"resultado={response.output_text}")
            print(
                f"usage input_tokens={getattr(response.usage, 'input_tokens', None)} "
                f"output_tokens={getattr(response.usage, 'output_tokens', None)}"
            )
            return 0
        except Exception as exc:
            print(f"Falha na chamada: {type(exc).__name__}")
            return 1
    print("Defina LLM_PROVIDER=gemini ou LLM_PROVIDER=openai no .env.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
