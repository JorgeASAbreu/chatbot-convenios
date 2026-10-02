from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.models import (
    ArrecadacaoRaw,
    Base,
    Convenio,
    ExecucaoRaw,
    Perfil,
    SourceSnapshot,
    Usuario,
)
from app.services.chatbot import ChatService
from app.services.convenios import ConvenioService
from app.services.financeiro import pendencia_texto, resumo_financeiro


def db():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    return Session(e)


def fixture(s):
    s.add_all(
        [
            Usuario(
                id=1,
                login="df",
                nome="DF",
                password_hash=hash_password("segura"),
                perfil=Perfil.DF.value,
            ),
            SourceSnapshot(
                id=1,
                resource_id="x",
                resource_name="x",
                resource_url="x",
                sha256="a",
                status="SUCCESS",
            ),
            Convenio(
                snapshot_id=1,
                codigo_siafi="9282916",
                codigo_sigcon="CV 33/2021",
                concedente="PREFEITURA MUNICIPAL PIRAPORA",
                objeto="cooperação",
                situacao_fonte="VIGENTE",
                termino_vigencia=date.today() - timedelta(days=1),
                source_row_hash="c",
            ),
        ]
    )
    for n, v in enumerate([Decimal("440000"), Decimal("80000"), Decimal("24204.43")]):
        s.add(
            ArrecadacaoRaw(
                snapshot_id=1,
                source_resource_id="x",
                source_file="x",
                source_row_number=n,
                source_row_hash=str(n),
                no_siafi="9282916",
                receita_arrecadada_r=v,
            )
        )
    s.add(
        ExecucaoRaw(
            snapshot_id=1,
            source_resource_id="x",
            source_file="x",
            source_row_number=4,
            source_row_hash="e",
            no_siafi="9282916",
            valor_empenhado=Decimal("520915"),
            valor_liquidado=Decimal("520915"),
            valor_pago=Decimal("519714.59"),
            tipo_registro="EMPENHO_CONVENIO",
        )
    )
    s.commit()


def test_password():
    assert verify_password("segura", hash_password("segura"))


def test_pirapora_financeiro():
    s = db()
    fixture(s)
    r = resumo_financeiro(s, "9282916")
    assert r.arrecadado == Decimal("544204.43") and r.pago == Decimal("519714.59")
    assert "1.200,41" in pendencia_texto(r)


def test_chat_context():
    s = db()
    fixture(s)
    u = s.get(Usuario, 1)
    assert "519.714,59" in ChatService(s, u).respond("quanto foi pago?", "9282916").texto


def test_concedente_normalizado_e_vigencia():
    s = db()
    fixture(s)
    c = ConvenioService(s).por_concedente("prefeitura municipal pirapora")[0]
    assert c.codigo_siafi == "9282916"
    assert ConvenioService.situacao(c) == ("VENCIDO", True)
