import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ControleInterno, Usuario
from app.llm.base import LLMProvider
from app.llm.contracts import ComposeContext, Intent
from app.llm.factory import provider as make_provider
from app.services.autorizacao import pode_consultar
from app.services.convenios import ConvenioService
from app.services.financeiro import pendencia_texto, resumo_financeiro
from app.services.intent_parser import parse_deterministic
from app.services.tools import ToolDispatcher


@dataclass
class ChatResponse:
    texto: str
    siafi: str | None = None
    detalhes: dict | None = None
    warning: str | None = None


def moeda(value: Decimal | None) -> str:
    return (
        f"R$ {(value or Decimal('0')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


class ChatService:
    def __init__(self, db: Session, usuario: Usuario, llm: LLMProvider | None = None):
        self.db, self.usuario, self.cs = db, usuario, ConvenioService(db)
        self.llm = llm or make_provider(get_settings(), db, usuario.id)

    def respond(self, pergunta: str, siafi_ativo: str | None = None) -> ChatResponse:
        classification = parse_deterministic(pergunta)
        warning = None
        plan = None
        if not classification:
            # Planner recebe somente pergunta/SIAFI; fatos só são expostos após autorização.
            llm_result = (
                self.llm.plan(pergunta, siafi_ativo)
                if hasattr(self.llm, "plan")
                else self.llm.classify_intent(pergunta, siafi_ativo)
            )
            plan, warning = getattr(llm_result, "plan", None), llm_result.warning
            classification = (
                type("Classification", (), {"intent": plan.intent})
                if plan
                else llm_result.classification
            )
        intent = classification.intent if classification else Intent.DESCONHECIDA
        if intent == Intent.NOVO_CONVENIO:
            return ChatResponse(
                "Contexto limpo. Informe o número SIAFI ou o concedente.", warning=warning
            )
        match = re.search(r"\b\d{5,}\b", pergunta)
        convenio = (
            self.cs.por_siafi(match.group() if match else siafi_ativo or "")
            if (match or siafi_ativo)
            else None
        )
        if not convenio and not match and not siafi_ativo:
            found = self.cs.por_concedente(pergunta)
            if len(found) == 1:
                convenio = found[0]
            elif len(found) > 1:
                return ChatResponse(
                    "Encontrei mais de um convênio: "
                    + "; ".join(f"{x.codigo_siafi} — {x.codigo_sigcon}" for x in found),
                    warning=warning,
                )
        if not convenio:
            return ChatResponse(
                "Convênio não localizado. Informe o número SIAFI ou o nome do concedente.",
                warning=warning,
            )
        if not pode_consultar(self.db, self.usuario, convenio):
            return ChatResponse("Acesso negado para este convênio.", warning=warning)
        if plan:
            try:
                facts = ToolDispatcher(self.db, self.usuario).execute(plan, convenio.codigo_siafi)
            except PermissionError:
                return ChatResponse("Acesso negado para este convênio.", warning=warning)
            composed = self.llm.compose(
                ComposeContext(question=pergunta, siafi_ativo=convenio.codigo_siafi, facts=facts)
            )
            safe_text = self._validated_composition(composed.text, facts)
            details = {
                "plan": plan.model_dump(mode="json"),
                "tools": [x.value for x in facts.tools_executed],
                "facts": facts.model_dump(mode="json"),
                "provider": self.llm.name,
                "compose": safe_text == composed.text and bool(composed.text),
            }
            return ChatResponse(
                safe_text or self._facts_template(facts),
                convenio.codigo_siafi,
                details,
                composed.warning or warning,
            )
        return self._execute(intent, convenio, warning)

    @staticmethod
    def _validated_composition(text: str | None, facts) -> str | None:
        """Rejeita números que pareçam valores, datas ou identificadores não consultados."""
        if not text or not text.strip():
            return None

        allowed_amounts: set[str] = set()
        allowed_dates: set[str] = set()

        def collect(value):
            if isinstance(value, Decimal):
                allowed_amounts.add(moeda(value))
                allowed_amounts.add(moeda(value.quantize(Decimal("0.01"))))
            elif isinstance(value, (date, datetime)):
                allowed_dates.add(value.strftime("%d/%m/%Y"))
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    collect(child)

        collect(facts.facts)
        allowed_amounts.update(
            moeda(value)
            for value in (
                facts.percentual_receitas_pactuadas_sobre_liquidado,
                facts.percentual_receitas_totais_sobre_liquidado,
            )
            if value is not None
        )
        for amount in re.findall(r"R\$\s*[\d.]+,\d{2}", text):
            normalized = "R$ " + amount.split("R$", 1)[1].strip()
            if normalized not in allowed_amounts:
                return None
        for percent in re.findall(r"\b\d+(?:[.,]\d+)?\s*%", text):
            number = percent.replace("%", "").strip()
            if "," in number:
                number = number.replace(".", "").replace(",", ".")
            try:
                value = Decimal(number).quantize(Decimal("0.01"))
            except Exception:
                return None
            allowed_percentages = {
                candidate.quantize(Decimal("0.01"))
                for candidate in (
                    facts.percentual_receitas_pactuadas_sobre_liquidado,
                    facts.percentual_receitas_totais_sobre_liquidado,
                )
                if candidate is not None
            }
            if value not in allowed_percentages:
                return None
        for mentioned_date in re.findall(r"\b\d{2}/\d{2}/\d{4}\b", text):
            if mentioned_date not in allowed_dates:
                return None
        siafis = re.findall(r"\b\d{7,}\b", text)
        if any(siafi != facts.siafi for siafi in siafis):
            return None
        return text.strip()

    @staticmethod
    def _facts_template(facts) -> str:
        basic = facts.facts.get("CONVENIO_BASICO", {})
        vigencia = facts.facts.get("VIGENCIA", {})
        arrec = facts.facts.get("ARRECADACAO", {})
        execucao = facts.facts.get("EXECUCAO_FINANCEIRA", {})
        pending = facts.facts.get("PENDENCIAS", {})
        lines = [
            "### Análise geral do convênio",
            f"**Convênio:** {basic.get('sigcon') or 'não informado'}",
            f"**SIAFI:** {facts.siafi}",
            f"**Concedente:** {basic.get('concedente') or 'não informado'}",
        ]
        if vigencia:
            inicio = vigencia.get("inicio_vigencia")
            termino = vigencia.get("termino_vigencia")
            if isinstance(inicio, (date, datetime)):
                inicio = inicio.strftime("%d/%m/%Y")
            if isinstance(termino, (date, datetime)):
                termino = termino.strftime("%d/%m/%Y")
            lines.extend(
                [
                    f"**Vigência:** {inicio or 'não informada'} a {termino or 'não informada'}",
                    f"Situação registrada na fonte: **{vigencia.get('situacao_fonte') or 'não informada'}**. Situação temporal calculada: **{vigencia.get('situacao_temporal_calculada') or 'não informada'}**.",
                ]
            )
        if arrec or execucao:
            lines.append("### Valores e execução financeira")
            values = basic
            if values.get("valor_total") is not None:
                lines.append(f"- Valor total do convênio: {moeda(values['valor_total'])}")
                lines.append(f"- Valor do concedente: {moeda(values.get('valor_concedente'))}")
                lines.append(f"- Valor do proponente: {moeda(values.get('valor_proponente'))}")
            if arrec:
                lines.extend(
                    [
                        f"- Arrecadado em receitas pactuadas: {moeda(arrec.get('receitas_pactuadas'))}",
                        f"- Rendimentos registrados: {moeda(arrec.get('rendimentos'))}",
                        f"- Total de receitas registradas, incluindo rendimentos: {moeda(arrec.get('receitas_totais_registradas'))}",
                    ]
                )
            if execucao:
                for label, key in (
                    ("Empenhado", "empenhado"),
                    ("Liquidado", "liquidado"),
                    ("Pago", "pago"),
                ):
                    lines.append(f"- {label}: {moeda(execucao.get(key))}")
        if facts.percentual_execucao_disponivel:
            percent = facts.percentual_receitas_pactuadas_sobre_liquidado.quantize(Decimal("0.01"))
            lines.extend(
                [
                    "### Percentual de execução",
                    f"Receitas pactuadas sobre liquidado: **{percent}%**.",
                ]
            )
        else:
            lines.extend(
                [
                    "### Percentual de execução",
                    "O percentual não pode ser calculado porque não há valor liquidado registrado na base consultada.",
                ]
            )
        difference = pending.get("liquidado_nao_pago", execucao.get("liquidado_nao_pago"))
        if difference is not None:
            lines.extend(
                [
                    "### Diferença entre liquidação e pagamento",
                    f"Há {moeda(difference)} liquidados que não constam como pagos na base consultada.",
                ]
            )
        attention = []
        if vigencia.get("alerta_inconsistencia"):
            attention.append("Há divergência entre a situação da fonte e o término da vigência.")
        if difference is not None and difference > 0:
            attention.append(
                f"Há {moeda(difference)} liquidados que não constam como pagos na base consultada."
            )
        if arrec.get("rendimentos"):
            attention.append(
                f"Há {moeda(arrec['rendimentos'])} de rendimentos registrados, apresentados separadamente das receitas pactuadas."
            )
        if attention:
            lines.append("### Pontos que merecem atenção")
            lines.extend(f"- {item}" for item in attention)
        return "\n\n".join(lines)

    def _execute(self, intent: Intent, convenio, warning: str | None) -> ChatResponse:
        resumo = resumo_financeiro(self.db, convenio.codigo_siafi)
        details = {"intent": intent.value, "financeiro": resumo.__dict__}
        if intent == Intent.PAGO:
            text = f"Constam {moeda(resumo.pago)} pagos no SIAFI {convenio.codigo_siafi}."
        elif intent == Intent.LIQUIDADO:
            text = f"Constam {moeda(resumo.liquidado)} liquidados no SIAFI {convenio.codigo_siafi}."
        elif intent == Intent.EMPENHADO:
            text = f"Constam {moeda(resumo.empenhado)} empenhados no SIAFI {convenio.codigo_siafi}."
        elif intent == Intent.ARRECADACAO:
            text = (
                f"Constam {moeda(resumo.arrecadado)} em receitas registradas no SIAFI "
                f"{convenio.codigo_siafi}."
            )
        elif intent == Intent.PENDENCIA_PAGAMENTO:
            text = (
                pendencia_texto(resumo)
                or "Não há diferença positiva entre liquidado e pago na base consultada."
            )
        elif intent == Intent.VALOR_TOTAL:
            text = f"O valor total pactuado do convênio é {moeda(convenio.valor_total_convenio_r)}."
        elif intent == Intent.VIGENCIA:
            temporal, inconsistencia = self.cs.situacao(convenio)
            details["vigencia"] = {
                "inicio": convenio.inicio_vigencia,
                "termino": convenio.termino_vigencia,
                "situacao_fonte": convenio.situacao_fonte,
                "situacao_temporal_calculada": temporal,
                "alerta_inconsistencia": inconsistencia,
            }
            text = (
                f"Vigência: {convenio.inicio_vigencia or 'não informada'} a "
                f"{convenio.termino_vigencia or 'não informada'}. Situação da fonte: "
                f"{convenio.situacao_fonte or 'não informada'}; situação temporal "
                f"calculada: {temporal or 'não informada'}."
            )
        elif intent == Intent.SITUACAO_GERAL:
            temporal, inconsistencia = self.cs.situacao(convenio)
            text = (
                f"Situação informada pela fonte: {convenio.situacao_fonte or 'não informada'}. "
                f"Situação temporal calculada: {temporal or 'não informada'}."
                + (
                    " Há inconsistência entre fonte e término de vigência."
                    if inconsistencia
                    else ""
                )
            )
            if resumo.percentual_receitas_pactuadas_sobre_liquidado is not None:
                text += f" Percentual de execução: {resumo.percentual_receitas_pactuadas_sobre_liquidado.quantize(Decimal('0.01'))}%."
        elif intent == Intent.RESUMO_FINANCEIRO:
            text = (
                f"Resumo: arrecadado {moeda(resumo.arrecadado)}, "
                f"empenhado {moeda(resumo.empenhado)}, liquidado "
                f"{moeda(resumo.liquidado)} e pago {moeda(resumo.pago)}."
            )
            if resumo.percentual_receitas_pactuadas_sobre_liquidado is not None:
                text += f" Percentual de execução: {resumo.percentual_receitas_pactuadas_sobre_liquidado.quantize(Decimal('0.01'))}%."
        elif intent == Intent.PERCENTUAL_EXECUCAO:
            if resumo.percentual_receitas_pactuadas_sobre_liquidado is None:
                text = "O percentual não pode ser calculado porque não há valor liquidado registrado na base consultada."
            else:
                text = f"Percentual de execução (receitas pactuadas sobre liquidado): {resumo.percentual_receitas_pactuadas_sobre_liquidado.quantize(Decimal('0.01'))}%."
        elif intent in (Intent.PM6, Intent.PROVIDENCIAS):
            controls = (
                self.db.query(ControleInterno).filter_by(codigo_siafi=convenio.codigo_siafi).all()
            )
            text = (
                "Não há informação interna cadastrada."
                if not controls
                else "Há informações internas cadastradas para consulta autorizada."
            )
        else:
            text = (
                f"SIAFI {convenio.codigo_siafi} — "
                f"{convenio.codigo_sigcon or 'sem SIGCON'} — {convenio.concedente or ''}."
            )
        return ChatResponse(text, convenio.codigo_siafi, details, warning)
