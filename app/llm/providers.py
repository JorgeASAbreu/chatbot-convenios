import json
import time
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import LlmUsage
from app.llm.base import LLMProvider
from app.llm.contracts import ComposeContext, IntentClassification, LLMCallResult, QueryPlan

PLAN_PROMPT = "Retorne somente JSON QueryPlan. Tools fechadas: CONVENIO_BASICO, VIGENCIA, VALORES_CONVENIO, ARRECADACAO, EXECUCAO_FINANCEIRA, PENDENCIAS, CONTROLES_INTERNOS, PM6, PROVIDENCIAS. Não calcule, não peça SQL e não invente valores ou SIAFI."
COMPOSE_PROMPT = "Responda somente com os fatos fornecidos. Não invente ou calcule valores/datas. Não chame diferença de saldo bancário ou dívida. Preserve situação da fonte e situação temporal."


class NoneProvider(LLMProvider):
    name = "none"

    def classify_intent(self, question, active_siafi):
        return LLMCallResult()

    def plan(self, question, active_siafi):
        return LLMCallResult()

    def compose(self, context):
        return LLMCallResult()

    def friendly(self, structured):
        return structured


class UsageTrackedProvider(LLMProvider):
    def __init__(self, settings: Settings, db: Session | None = None, user_id: int | None = None):
        self.settings, self.db, self.user_id = settings, db, user_id

    def _spent(self):
        if not self.db:
            return Decimal("0")
        return self.db.scalar(
            select(func.coalesce(func.sum(LlmUsage.estimated_cost), 0)).where(
                LlmUsage.provider == self.name, LlmUsage.success.is_(True)
            )
        ) or Decimal("0")

    def _record(self, operation, in_tokens, out_tokens, latency, success, siafi=None, error=None):
        cost = Decimal("0")
        if self.name == "gemini":
            cost = (
                Decimal(in_tokens) * self.settings.gemini_cost_input_per_1m
                + Decimal(out_tokens) * self.settings.gemini_cost_output_per_1m
            ) / Decimal("1000000")
        if self.db:
            self.db.add(
                LlmUsage(
                    provider=self.name,
                    model=self.model,
                    operation=operation,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    estimated_cost=cost,
                    latency_ms=latency,
                    success=success,
                    error=error,
                    user_id=self.user_id,
                    siafi=siafi,
                )
            )
            self.db.commit()
        return cost

    def _allowed(self):
        spent = self._spent()
        if spent >= self.settings.gemini_budget_usd:
            return False, "Teto local de orçamento Gemini atingido; nenhuma chamada foi realizada."
        if spent >= self.settings.gemini_budget_usd * self.settings.gemini_warn_threshold:
            return True, "Aviso: o consumo local Gemini atingiu o limite de alerta configurado."
        return True, None


class GeminiProvider(UsageTrackedProvider):
    name = "gemini"

    @property
    def model(self):
        return self.settings.gemini_model

    def _call(self, operation, prompt, siafi=None):
        if not self.settings.gemini_enabled:
            return LLMCallResult()
        allowed, warning = self._allowed()
        if not allowed:
            return LLMCallResult(warning=warning)
        started = time.perf_counter()
        try:
            from google import genai

            r = genai.Client(api_key=self.settings.gemini_api_key).models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                    if operation == "PLAN"
                    else "text/plain"
                },
            )
            u = getattr(r, "usage_metadata", None)
            self._record(
                operation,
                int(getattr(u, "prompt_token_count", 0) or 0),
                int(getattr(u, "candidates_token_count", 0) or 0),
                int((time.perf_counter() - started) * 1000),
                True,
                siafi,
            )
            return LLMCallResult(text=getattr(r, "text", ""), warning=warning)
        except Exception as exc:
            self._record(
                operation, 0, 0, int((time.perf_counter() - started) * 1000), False, siafi, str(exc)
            )
            return LLMCallResult(warning=warning)

    def plan(self, question, active_siafi):
        x = self._call(
            "PLAN",
            f"{PLAN_PROMPT}\nSIAFI ativo: {active_siafi or 'nenhum'}\nPergunta: {question}",
            active_siafi,
        )
        if x.text:
            try:
                x.plan = QueryPlan.model_validate(json.loads(x.text))
            except Exception:
                pass
        return x

    def compose(self, context: ComposeContext):
        return self._call(
            "COMPOSE",
            f"{COMPOSE_PROMPT}\nPergunta: {context.question}\nFATOS: {context.facts.model_dump_json()}",
            context.siafi_ativo,
        )

    def classify_intent(self, question, active_siafi):
        x = self.plan(question, active_siafi)
        if x.plan:
            x.classification = IntentClassification(
                intent=x.plan.intent, confidence=x.plan.confidence
            )
        return x

    def friendly(self, structured):
        return structured


class OpenAIProvider(GeminiProvider):
    name = "openai"

    @property
    def model(self):
        return self.settings.openai_model

    def _call(self, operation, prompt, siafi=None):
        if not self.settings.openai_enabled:
            return LLMCallResult()
        started = time.perf_counter()
        try:
            from openai import OpenAI

            r = OpenAI(api_key=self.settings.openai_api_key).responses.create(
                model=self.model, input=prompt
            )
            u = r.usage
            self._record(
                operation,
                u.input_tokens,
                u.output_tokens,
                int((time.perf_counter() - started) * 1000),
                True,
                siafi,
            )
            return LLMCallResult(text=r.output_text)
        except Exception as exc:
            self._record(
                operation, 0, 0, int((time.perf_counter() - started) * 1000), False, siafi, str(exc)
            )
            return LLMCallResult()
