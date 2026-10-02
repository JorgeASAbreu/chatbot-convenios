"""Dispatcher fechado das ferramentas internas; não existe ferramenta SQL genérica."""

from sqlalchemy.orm import Session

from app.db.models import ControleInterno, Usuario
from app.llm.contracts import FactsBundle, InternalTool, QueryPlan, ToolResult
from app.services.autorizacao import pode_consultar
from app.services.convenios import ConvenioService
from app.services.financeiro import resumo_financeiro


class ToolDispatcher:
    def __init__(self, db: Session, usuario: Usuario):
        self.db, self.usuario = db, usuario

    def execute(self, plan: QueryPlan, siafi: str) -> FactsBundle:
        convenio = ConvenioService(self.db).por_siafi(siafi)
        if not convenio or not pode_consultar(self.db, self.usuario, convenio):
            raise PermissionError("Convênio inexistente ou não autorizado.")
        results = [self._one(tool, convenio) for tool in dict.fromkeys(plan.tools)]
        facts = {result.tool.value: result.data for result in results}
        resumo = resumo_financeiro(self.db, siafi)
        return FactsBundle(
            siafi=siafi,
            facts=facts,
            tools_executed=[result.tool for result in results],
            percentual_receitas_pactuadas_sobre_liquidado=resumo.percentual_receitas_pactuadas_sobre_liquidado,
            percentual_receitas_totais_sobre_liquidado=resumo.percentual_receitas_totais_sobre_liquidado,
            percentual_execucao_disponivel=resumo.percentual_receitas_pactuadas_sobre_liquidado
            is not None,
        )

    def _one(self, tool: InternalTool, convenio) -> ToolResult:
        cs = ConvenioService(self.db)
        if tool == InternalTool.CONVENIO_BASICO:
            data = {
                "sigcon": convenio.codigo_sigcon,
                "siafi": convenio.codigo_siafi,
                "concedente": convenio.concedente,
                "objeto": convenio.objeto,
                "situacao_fonte": convenio.situacao_fonte,
                "valor_total": convenio.valor_total_convenio_r,
                "valor_concedente": convenio.valor_concedente_r,
                "valor_proponente": convenio.valor_proponente_r,
            }
        elif tool == InternalTool.VIGENCIA:
            temporal, inconsistent = cs.situacao(convenio)
            data = {
                "inicio_vigencia": convenio.inicio_vigencia,
                "termino_vigencia": convenio.termino_vigencia,
                "situacao_fonte": convenio.situacao_fonte,
                "situacao_temporal_calculada": temporal,
                "alerta_inconsistencia": inconsistent,
            }
        elif tool == InternalTool.VALORES_CONVENIO:
            data = {
                "valor_proponente": convenio.valor_proponente_r,
                "valor_concedente": convenio.valor_concedente_r,
                "valor_total": convenio.valor_total_convenio_r,
            }
        elif tool in (
            InternalTool.ARRECADACAO,
            InternalTool.EXECUCAO_FINANCEIRA,
            InternalTool.PENDENCIAS,
        ):
            r = resumo_financeiro(self.db, convenio.codigo_siafi)
            data = {
                "arrecadado": r.receitas_pactuadas,
                "receitas_pactuadas": r.receitas_pactuadas,
                "rendimentos": r.rendimentos,
                "receitas_totais_registradas": r.arrecadado,
                "empenhado": r.empenhado,
                "liquidado": r.liquidado,
                "pago": r.pago,
                "liquidado_nao_pago": r.diferenca_liquidado_pago,
                "percentual_execucao": r.percentual_execucao,
                "percentual_receitas_pactuadas_sobre_liquidado": r.percentual_receitas_pactuadas_sobre_liquidado,
                "percentual_receitas_totais_sobre_liquidado": r.percentual_receitas_totais_sobre_liquidado,
                "percentual_execucao_disponivel": r.percentual_receitas_pactuadas_sobre_liquidado
                is not None,
            }
        else:
            controls = (
                self.db.query(ControleInterno).filter_by(codigo_siafi=convenio.codigo_siafi).all()
            )
            data = (
                {"informacao_interna": [x.descricao for x in controls]}
                if controls
                else {"informacao_interna": None}
            )
        return ToolResult(tool=tool, data=data)
