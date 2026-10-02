"""Ingestão de CSVs físicos: DataStore CKAN não participa da fonte de verdade."""

import csv
import hashlib
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ArrecadacaoRaw, Convenio, ExecucaoRaw, SourceSnapshot

PACKAGE_URL = "https://dados.mg.gov.br/api/3/action/package_show?id=portal_convenios_entrada"
RESOURCE_IDS = {
    "arrecadacao": "9eec029f-b12b-4056-9855-bfcc5ee5c712",
    "convenios": "b71a912c-a3a3-4e3e-b773-24c9d7a9c1b6",
    "execucao": "671e7701-145c-45ad-93fd-905abc46bcca",
    "execucao2": "d3742a25-5cc8-4224-9f4b-d77c30979660",
    "execucao3": "8b7c700f-8dcb-40e4-ab83-04240cbaf17a",
    "execucao4": "aa3800f5-3644-46e2-bdf9-01773abe06ec",
}


def val(v: str | None) -> Decimal | None:
    if not v or not v.strip():
        return None
    try:
        return Decimal(v.strip().replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def dat(v: str | None) -> date | None:
    if not v:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            pass
    return None


def field(row: dict, *names: str) -> str | None:
    normalized = {k.strip().lower(): v for k, v in row.items() if k}
    return next(
        (normalized.get(n.lower()) for n in names if normalized.get(n.lower()) is not None), None
    )


class DadosMGSyncService:
    def __init__(self, db: Session, proxy: str = "") -> None:
        self.db, self.proxy = db, proxy or None

    def resources(self) -> dict[str, dict]:
        r = httpx.get(PACKAGE_URL, proxy=self.proxy, timeout=60)
        r.raise_for_status()
        resources = r.json()["result"]["resources"]
        by_id = {x["id"]: x for x in resources}
        return {kind: by_id[rid] for kind, rid in RESOURCE_IDS.items() if rid in by_id}

    def sync_all(self) -> list[SourceSnapshot]:
        return [self.sync_resource(k, x) for k, x in self.resources().items()]

    def sync_resource(self, kind: str, resource: dict) -> SourceSnapshot:
        last = resource.get("last_modified") or resource.get("metadata_modified")
        prior = self.db.scalar(
            select(SourceSnapshot).where(
                SourceSnapshot.resource_id == resource["id"],
                SourceSnapshot.source_last_modified == last,
                SourceSnapshot.status == "SUCCESS",
            )
        )
        if prior:
            return prior
        response = httpx.get(resource["url"], proxy=self.proxy, timeout=180)
        response.raise_for_status()
        content = response.content
        digest = hashlib.sha256(content).hexdigest()
        existing = self.db.scalar(
            select(SourceSnapshot).where(
                SourceSnapshot.resource_id == resource["id"], SourceSnapshot.sha256 == digest
            )
        )
        if existing:
            return existing
        snap = SourceSnapshot(
            resource_id=resource["id"],
            resource_name=resource.get("name", kind),
            resource_url=resource["url"],
            source_last_modified=last,
            sha256=digest,
        )
        self.db.add(snap)
        self.db.flush()
        try:
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";"))
            for n, row in enumerate(rows, 2):
                self._ingest(kind, snap, n, row)
            snap.row_count, snap.status = len(rows), "SUCCESS"
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            snap.status, snap.error_message = "ERROR", str(exc)[:1000]
            self.db.add(snap)
            self.db.commit()
            raise
        return snap

    def _ingest(self, kind: str, snap: SourceSnapshot, n: int, row: dict) -> None:
        raw_hash = hashlib.sha256("|".join(str(v or "") for v in row.values()).encode()).hexdigest()
        provenance = dict(
            snapshot_id=snap.id,
            source_resource_id=snap.resource_id,
            source_file=snap.resource_name,
            source_row_number=n,
            source_last_modified=snap.source_last_modified,
            source_row_hash=raw_hash,
        )
        if kind == "convenios":
            siafi = field(row, "codigo_siafi")
            if not siafi:
                return
            c = Convenio(
                snapshot_id=snap.id,
                source_row_hash=raw_hash,
                codigo_siafi=siafi,
                codigo_sigcon=field(row, "codigo_sigcon"),
                concedente=field(row, "concedente"),
                objeto=field(row, "objeto"),
                situacao_fonte=field(row, "situacao"),
                unidade_orcamentaria=field(row, "unidade_orcamentaria"),
                inicio_vigencia=dat(field(row, "inicio_vigencia")),
                termino_vigencia=dat(field(row, "termino_vigencia")),
                valor_proponente_r=val(field(row, "valor_proponente_r")),
                valor_concedente_r=val(field(row, "valor_concedente_r")),
                valor_total_convenio_r=val(field(row, "valor_total_convenio_r")),
            )
            c.situacao_temporal_calculada = (
                "ENCERRADA"
                if c.termino_vigencia and c.termino_vigencia < date.today()
                else c.situacao_fonte
            )
            c.alerta_inconsistencia = (
                c.situacao_fonte == "VIGENTE" and c.situacao_temporal_calculada == "ENCERRADA"
            )
            self.db.add(c)
        elif kind == "arrecadacao":
            self.db.add(
                ArrecadacaoRaw(
                    **provenance,
                    uo=field(row, "uo"),
                    tipo_siafi=field(row, "tipo_siafi"),
                    no_siafi=field(row, "no_siafi") or "",
                    ano_exercicio_receita=int(field(row, "ano_exercicio_receita") or 0) or None,
                    tipo_de_receita=field(row, "tipo_de_receita"),
                    fonte=field(row, "fonte"),
                    receita_arrecadada_r=val(field(row, "receita_arrecadada_r")),
                    data_da_arrecadacao=dat(field(row, "data_da_arrecadacao")),
                )
            )
        else:
            siafi, empenho, credor = (
                field(row, "no_siafi") or "",
                field(row, "no_empenho") or "",
                field(row, "cnpj_cpf_credor") or "",
            )
            tipo = (
                "REGISTRO_ESPECIAL"
                if siafi == "0" and empenho == "0" and credor == "99999999999999"
                else (
                    "REGISTRO_SEM_SIAFI"
                    if siafi == "0"
                    else "REGISTRO_SEM_EMPENHO"
                    if empenho == "0"
                    else "EMPENHO_CONVENIO"
                )
            )
            self.db.add(
                ExecucaoRaw(
                    **provenance,
                    uo=field(row, "uo"),
                    tipo_siafi=field(row, "tipo_siafi"),
                    no_siafi=siafi,
                    ano_empenho=int(field(row, "ano_empenho") or 0) or None,
                    no_empenho=empenho,
                    ue=field(row, "ue"),
                    data_empenho=dat(field(row, "data_empenho")),
                    cnpj_cpf_credor=credor,
                    razao_social_credor=field(row, "razao_social_credor"),
                    valor_empenhado=val(field(row, "valor_empenhado", "valor_empenhado_r")),
                    valor_liquidado=val(field(row, "valor_liquidado", "valor_liquidado_r")),
                    valor_pago=val(field(row, "valor_pago", "valor_pago_r")),
                    tipo_registro=tipo,
                )
            )
