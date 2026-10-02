from datetime import date, timedelta
from decimal import Decimal

import pytest
from test_core import db, fixture

from app.core.config import Settings
from app.db.models import LlmUsage, Usuario
from app.llm.contracts import Intent, IntentClassification, LLMCallResult
from app.llm.providers import GeminiProvider
from app.services.chatbot import ChatService
from app.services.intent_parser import parse_deterministic


class FakeLLM:
    def __init__(self, intent: Intent | None = None, warning: str | None = None):
        self.intent, self.warning, self.calls = intent, warning, []

    def classify_intent(self, question, active_siafi):
        self.calls.append((question, active_siafi))
        classification = (
            IntentClassification(intent=self.intent, confidence=0.9) if self.intent else None
        )
        return LLMCallResult(classification=classification, warning=self.warning)

    def friendly(self, structured):
        return structured


@pytest.fixture
def prepared():
    session = db()
    fixture(session)
    convenio = session.get(__import__("app.db.models", fromlist=["Convenio"]).Convenio, 1)
    convenio.inicio_vigencia = date.today() - timedelta(days=30)
    convenio.valor_total_convenio_r = Decimal("624000")
    session.commit()
    return session, session.get(Usuario, 1)


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("qual a vigência?", Intent.VIGENCIA),
        ("qual o valor total do convênio?", Intent.VALOR_TOTAL),
        ("quanto foi arrecadado?", Intent.ARRECADACAO),
        ("situação geral", Intent.SITUACAO_GERAL),
        ("Me dê um resumo financeiro desse convênio.", Intent.RESUMO_FINANCEIRO),
        ("quanto foi empenhado?", Intent.EMPENHADO),
        ("falta pagar?", Intent.PENDENCIA_PAGAMENTO),
    ],
)
def test_deterministic_parser(question, intent):
    assert parse_deterministic(question).intent == intent


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (Intent.VIGENCIA, "Situação da fonte: VIGENTE"),
        (Intent.VALOR_TOTAL, "624.000,00"),
        (Intent.ARRECADACAO, "544.204,43"),
        (Intent.SITUACAO_GERAL, "Situação temporal calculada: VENCIDO"),
        (Intent.RESUMO_FINANCEIRO, "519.714,59"),
    ],
)
def test_intents_use_deterministic_services(prepared, intent, expected):
    session, user = prepared
    fake = FakeLLM(intent)
    response = ChatService(session, user, fake).respond("pergunta livre", "9282916")
    assert expected in response.texto
    assert fake.calls == [("pergunta livre", "9282916")]


def test_llm_fallback_and_active_context(prepared):
    session, user = prepared
    fake = FakeLLM(Intent.VALOR_TOTAL)
    response = ChatService(session, user, fake).respond("qual montante pactuado?", "9282916")
    assert "624.000,00" in response.texto
    assert fake.calls == [("qual montante pactuado?", "9282916")]


def test_llm_invalid_or_unavailable_falls_back_safely(prepared):
    session, user = prepared
    response = ChatService(session, user, FakeLLM()).respond("pergunta obscura", "9282916")
    assert "SIAFI 9282916" in response.texto


def test_gemini_disabled_does_not_call_or_persist(prepared):
    session, _ = prepared
    provider = GeminiProvider(Settings(gemini_enabled=False), session)
    assert provider.classify_intent("texto", "9282916").classification is None
    assert session.query(LlmUsage).count() == 0


def test_gemini_budget_cap_blocks_call(prepared):
    session, _ = prepared
    settings = Settings(gemini_enabled=True, gemini_budget_usd=Decimal("5"))
    session.add(
        LlmUsage(
            provider="gemini",
            model="x",
            input_tokens=1,
            output_tokens=1,
            estimated_cost=Decimal("5"),
            latency_ms=1,
            success=True,
        )
    )
    session.commit()
    result = GeminiProvider(settings, session).classify_intent("texto", "9282916")
    assert result.classification is None and "Teto local" in result.warning


def test_gemini_threshold_warning(prepared):
    session, _ = prepared
    settings = Settings(
        gemini_enabled=True, gemini_budget_usd=Decimal("5"), gemini_warn_threshold=Decimal("0.8")
    )
    session.add(
        LlmUsage(
            provider="gemini",
            model="x",
            input_tokens=1,
            output_tokens=1,
            estimated_cost=Decimal("4"),
            latency_ms=1,
            success=True,
        )
    )
    session.commit()
    allowed, warning = GeminiProvider(settings, session)._allowed()
    assert allowed and warning


def test_token_accounting_is_persisted(prepared):
    session, _ = prepared
    settings = Settings(
        gemini_cost_input_per_1m=Decimal("1"), gemini_cost_output_per_1m=Decimal("2")
    )
    provider = GeminiProvider(settings, session)
    provider._record("model", 1000000, 500000, 12, True)
    usage = session.query(LlmUsage).one()
    assert usage.estimated_cost == Decimal("2.000000")
    assert usage.input_tokens == 1000000 and usage.output_tokens == 500000


def test_financial_values_are_not_taken_from_llm(prepared):
    session, user = prepared
    fake = FakeLLM(Intent.PAGO)
    response = ChatService(session, user, fake).respond("texto sem valor informado", "9282916")
    assert "519.714,59" in response.texto
