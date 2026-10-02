"""Exercita os provedores com SDKs simulados, sem acesso à rede."""

from types import SimpleNamespace

import pytest
from test_core import db, fixture

from app.core.config import Settings
from app.db.models import LlmUsage, Usuario
from app.llm.providers import GeminiProvider, OpenAIProvider
from app.services.chatbot import ChatService


class HTTPFailure(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}")


def provider_with_fake_sdk(monkeypatch, kind, outcomes):
    """Uma tentativa do backend corresponde a uma chamada fake do SDK."""
    attempts = []
    sleeps = []
    monkeypatch.setattr("app.llm.providers.time.sleep", sleeps.append)

    def call(**kwargs):
        attempts.append(kwargs)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if kind == "gemini":
            return SimpleNamespace(
                text=outcome,
                usage_metadata=SimpleNamespace(prompt_token_count=7, candidates_token_count=3),
            )
        return SimpleNamespace(
            output_text=outcome,
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
        )

    if kind == "gemini":
        monkeypatch.setattr(
            "google.genai.Client",
            lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=call)),
        )
        settings = Settings(gemini_enabled=True, gemini_model="modelo-fake")
        provider_class = GeminiProvider
    else:
        monkeypatch.setattr(
            "openai.OpenAI",
            lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(create=call)),
        )
        settings = Settings(openai_enabled=True, openai_model="modelo-fake")
        provider_class = OpenAIProvider
    session = db()
    fixture(session)
    return provider_class(settings, session, 1), session, attempts, sleeps


@pytest.mark.parametrize("kind", ["gemini", "openai"])
@pytest.mark.parametrize("error", [HTTPFailure(503), HTTPFailure(429), TimeoutError("timed out")])
def test_retry_then_success_records_each_attempt(monkeypatch, kind, error):
    provider, session, attempts, sleeps = provider_with_fake_sdk(
        monkeypatch, kind, [error, "ok"]
    )
    result = provider._call("PLAN", "pergunta", "9282916")
    assert result.text == "ok"
    assert len(attempts) == 2 and sleeps == [0.25]
    usage = session.query(LlmUsage).order_by(LlmUsage.id).all()
    assert [(row.operation, row.success) for row in usage] == [("PLAN", False), ("PLAN", True)]
    assert usage[0].error and usage[1].input_tokens == 7 and usage[1].output_tokens == 3
    assert all(row.siafi == "9282916" and row.user_id == 1 for row in usage)


@pytest.mark.parametrize("kind", ["gemini", "openai"])
@pytest.mark.parametrize("status", [401, 403, 404])
def test_non_retryable_status_stops_immediately(monkeypatch, kind, status):
    provider, session, attempts, sleeps = provider_with_fake_sdk(
        monkeypatch, kind, [HTTPFailure(status)]
    )
    result = provider._call("PLAN", "pergunta", "9282916")
    assert result.text is None and result.warning
    assert len(attempts) == 1 and sleeps == []
    usage = session.query(LlmUsage).one()
    assert not usage.success and str(status) in usage.error


@pytest.mark.parametrize("kind", ["gemini", "openai"])
def test_three_503s_use_safe_fallback(monkeypatch, kind):
    provider, session, attempts, sleeps = provider_with_fake_sdk(
        monkeypatch, kind, [HTTPFailure(503) for _ in range(3)]
    )
    response = ChatService(session, session.get(Usuario, 1), provider).respond(
        "como anda esse convênio?", "9282916"
    )
    assert len(attempts) == 3 and sleeps == [0.25, 0.5]
    assert "temporariamente indisponível" in response.texto
    assert "CV 33/2021" not in response.texto
    assert session.query(LlmUsage).filter_by(operation="PLAN", success=False).count() == 3


def test_budget_limit_skips_sdk(monkeypatch):
    provider, session, attempts, _ = provider_with_fake_sdk(monkeypatch, "gemini", ["ok"])
    provider.settings.gemini_budget_usd = 0
    result = provider._call("PLAN", "pergunta", "9282916")
    assert "Teto local" in result.warning and attempts == []
    assert session.query(LlmUsage).count() == 0


def test_fake_sdk_runs_plan_tools_facts_and_compose(monkeypatch):
    plan = '{"intent":"PAGO","tools":["EXECUCAO_FINANCEIRA"],"needs_active_siafi":true,"confidence":0.99}'
    provider, session, attempts, _ = provider_with_fake_sdk(
        monkeypatch, "gemini", [plan, "Constam R$ 519.714,59 pagos."]
    )
    response = ChatService(session, session.get(Usuario, 1), provider).respond(
        "9282916 quanto foi pago?"
    )
    assert response.texto == "Constam R$ 519.714,59 pagos."
    assert response.detalhes["facts"]["facts"]["EXECUCAO_FINANCEIRA"]["pago"] == "519714.59"
    assert "quanto foi pago?" in attempts[0]["contents"]
    assert "519714.59" in attempts[1]["contents"]
    assert [row.operation for row in session.query(LlmUsage).order_by(LlmUsage.id)] == [
        "PLAN", "COMPOSE"
    ]


def test_llm_usage_model_matches_audited_columns_and_foreign_key():
    table = LlmUsage.__table__
    assert set(table.columns.keys()) >= {
        "provider", "model", "operation", "input_tokens", "output_tokens",
        "estimated_cost", "latency_ms", "success", "error", "user_id", "siafi", "timestamp",
    }
    assert any(
        foreign_key.parent.name == "user_id" and foreign_key.column.table.name == "usuarios"
        for foreign_key in table.foreign_keys
    )
