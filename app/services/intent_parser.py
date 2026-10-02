import unicodedata

from app.llm.contracts import Intent, IntentClassification


def _normal(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )


def parse_deterministic(question: str) -> IntentClassification | None:
    """Rotas inequívocas não consomem IA, são previsíveis e auditáveis."""
    text = _normal(question)
    rules = (
        (Intent.NOVO_CONVENIO, ("novo convenio", "reiniciar")),
        (Intent.PENDENCIA_PAGAMENTO, ("falta pagar", "pendencia", "pendencias")),
        (Intent.RESUMO_FINANCEIRO, ("resumo financeiro", "resumo do convenio")),
        (
            Intent.PERCENTUAL_EXECUCAO,
            ("percentual de execucao", "percentual arrecadado", "quanto do liquidado"),
        ),
        (Intent.VALOR_TOTAL, ("valor total", "valor do convenio", "valor pactuado")),
        (Intent.VIGENCIA, ("vigencia", "quando vence", "vence")),
        (Intent.SITUACAO_GERAL, ("situacao geral", "situacao do convenio", "situacao")),
        (Intent.ARRECADACAO, ("arrecad", "receita")),
        (Intent.LIQUIDADO, ("liquidad",)),
        (Intent.EMPENHADO, ("empenhad",)),
        (Intent.PAGO, ("pagamento", "pago", "pagos")),
        (Intent.PM6, ("pm/6", "pm6")),
        (Intent.PROVIDENCIAS, ("providencia", "providencias")),
    )
    for intent, needles in rules:
        if any(needle in text for needle in needles):
            return IntentClassification(intent=intent, confidence=1.0)
    return None
