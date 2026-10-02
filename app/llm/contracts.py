"""Contratos estritos entre classificação linguística e serviços determinísticos."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    VIGENCIA = "VIGENCIA"
    VALOR_TOTAL = "VALOR_TOTAL"
    ARRECADACAO = "ARRECADACAO"
    PAGO = "PAGO"
    LIQUIDADO = "LIQUIDADO"
    EMPENHADO = "EMPENHADO"
    PENDENCIA_PAGAMENTO = "PENDENCIA_PAGAMENTO"
    SITUACAO_GERAL = "SITUACAO_GERAL"
    RESUMO_FINANCEIRO = "RESUMO_FINANCEIRO"
    PERCENTUAL_EXECUCAO = "PERCENTUAL_EXECUCAO"
    PM6 = "PM6"
    PROVIDENCIAS = "PROVIDENCIAS"
    NOVO_CONVENIO = "NOVO_CONVENIO"
    DESCONHECIDA = "DESCONHECIDA"


class IntentClassification(BaseModel):
    """O modelo só pode selecionar rota; não recebe nem produz valores financeiros."""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    confidence: float


class LLMCallResult(BaseModel):
    classification: IntentClassification | None = None
    plan: "QueryPlan | None" = None
    text: str | None = None
    warning: str | None = None


class InternalTool(StrEnum):
    CONVENIO_BASICO = "CONVENIO_BASICO"
    VIGENCIA = "VIGENCIA"
    VALORES_CONVENIO = "VALORES_CONVENIO"
    ARRECADACAO = "ARRECADACAO"
    EXECUCAO_FINANCEIRA = "EXECUCAO_FINANCEIRA"
    PENDENCIAS = "PENDENCIAS"
    CONTROLES_INTERNOS = "CONTROLES_INTERNOS"
    PM6 = "PM6"
    PROVIDENCIAS = "PROVIDENCIAS"


class QueryPlan(BaseModel):
    """Plano fechado: o modelo pede dados, mas não parametriza consultas nem permissões."""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    tools: list[InternalTool] = Field(min_length=1, max_length=9)
    needs_active_siafi: bool = True
    confidence: float = Field(ge=0, le=1)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: InternalTool
    data: dict


class FactsBundle(BaseModel):
    """Somente fatos autorizados e calculados pelo backend podem chegar ao Composer."""

    model_config = ConfigDict(extra="forbid")
    siafi: str
    facts: dict[str, dict]
    tools_executed: list[InternalTool]
    percentual_arrecadado_sobre_liquidado: Decimal | None = None
    percentual_execucao_disponivel: bool = False


class ComposeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    siafi_ativo: str
    facts: FactsBundle
