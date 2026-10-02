from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ArrecadacaoRaw, ExecucaoRaw


@dataclass
class ResumoFinanceiro:
    arrecadado: Decimal
    empenhado: Decimal
    liquidado: Decimal
    pago: Decimal

    @property
    def diferenca_liquidado_pago(self) -> Decimal:
        return self.liquidado - self.pago

    @property
    def percentual_arrecadado_sobre_liquidado(self) -> Decimal | None:
        """Indicador oficial deste sistema: arrecadado / liquidado * 100."""
        if self.liquidado == 0:
            return None
        return (self.arrecadado / self.liquidado) * Decimal("100")


def _sum(db: Session, column, siafi: str) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(column), 0)).where(column.class_.no_siafi == siafi)
    ) or Decimal("0")


def resumo_financeiro(db: Session, siafi: str) -> ResumoFinanceiro:
    return ResumoFinanceiro(
        _sum(db, ArrecadacaoRaw.receita_arrecadada_r, siafi),
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
