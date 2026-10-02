from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ArrecadacaoRaw, ExecucaoRaw


@dataclass
class ResumoFinanceiro:
    arrecadado: Decimal
    receitas_pactuadas: Decimal
    rendimentos: Decimal
    empenhado: Decimal
    liquidado: Decimal
    pago: Decimal

    @property
    def diferenca_liquidado_pago(self) -> Decimal:
        return self.liquidado - self.pago

    @property
    def percentual_receitas_pactuadas_sobre_liquidado(self) -> Decimal | None:
        """Percentual de execução oficial: receitas pactuadas / liquidado * 100."""
        if self.liquidado == 0:
            return None
        return (self.receitas_pactuadas / self.liquidado) * Decimal("100")

    @property
    def percentual_receitas_totais_sobre_liquidado(self) -> Decimal | None:
        if self.liquidado == 0:
            return None
        return (self.arrecadado / self.liquidado) * Decimal("100")

    @property
    def percentual_arrecadado_sobre_liquidado(self) -> Decimal | None:
        """Compatibilidade: percentual de execução é o de receitas pactuadas."""
        return self.percentual_receitas_pactuadas_sobre_liquidado

    @property
    def percentual_execucao(self) -> Decimal | None:
        """Execução percentual = receitas pactuadas / liquidado × 100."""
        return self.percentual_receitas_pactuadas_sobre_liquidado


def _sum(db: Session, column, siafi: str) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(column), 0)).where(column.class_.no_siafi == siafi)
    ) or Decimal("0")


def resumo_financeiro(db: Session, siafi: str) -> ResumoFinanceiro:
    receitas = db.scalars(select(ArrecadacaoRaw).where(ArrecadacaoRaw.no_siafi == siafi)).all()
    # Rendimentos são reconhecidos pela classificação publicada; linhas sem indicação permanecem pactuadas.
    rendimentos = sum(
        (
            row.receita_arrecadada_r or Decimal("0")
            for row in receitas
            if "rendimento" in (row.tipo_de_receita or "").lower()
        ),
        Decimal("0"),
    )
    total = sum((row.receita_arrecadada_r or Decimal("0") for row in receitas), Decimal("0"))
    return ResumoFinanceiro(
        total,
        total - rendimentos,
        rendimentos,
        _sum(db, ExecucaoRaw.valor_empenhado, siafi),
        _sum(db, ExecucaoRaw.valor_liquidado, siafi),
        _sum(db, ExecucaoRaw.valor_pago, siafi),
    )


def pendencia_texto(resumo: ResumoFinanceiro) -> str | None:
    if resumo.diferenca_liquidado_pago > 0:
        return (
            (
                f"Há R$ {resumo.diferenca_liquidado_pago:,.2f} liquidados que não constam "
                "como pagos na base consultada."
            )
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    return None
