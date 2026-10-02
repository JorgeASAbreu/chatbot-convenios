from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Perfil(StrEnum):
    UNIDADE = "UNIDADE"
    DF = "DF"
    ADMIN = "ADMIN"


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(180))
    password_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(20), default=Perfil.UNIDADE.value)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Unidade(Base):
    __tablename__ = "unidades"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(180))


class UsuarioUnidade(Base):
    __tablename__ = "usuario_unidades"
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), primary_key=True)


class Convenio(Base):
    __tablename__ = "convenios"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id"))
    unidade_orcamentaria: Mapped[str | None] = mapped_column(String(30))
    codigo_sigcon: Mapped[str | None] = mapped_column(String(80), index=True)
    codigo_uniao: Mapped[str | None] = mapped_column(String(80))
    codigo_plano_de_trabalho: Mapped[str | None] = mapped_column(String(80))
    codigo_siafi: Mapped[str] = mapped_column(String(30), index=True)
    sei: Mapped[str | None] = mapped_column(String(100))
    instrumento: Mapped[str | None] = mapped_column(String(100))
    titulo: Mapped[str | None] = mapped_column(Text)
    proponente: Mapped[str | None] = mapped_column(Text)
    concedente: Mapped[str | None] = mapped_column(Text, index=True)
    esfera_concedente: Mapped[str | None] = mapped_column(String(100))
    objeto: Mapped[str | None] = mapped_column(Text)
    situacao_fonte: Mapped[str | None] = mapped_column(String(80))
    situacao_temporal_calculada: Mapped[str | None] = mapped_column(String(30))
    alerta_inconsistencia: Mapped[bool] = mapped_column(Boolean, default=False)
    inicio_vigencia: Mapped[date | None] = mapped_column(Date)
    termino_vigencia: Mapped[date | None] = mapped_column(Date)
    valor_proponente_r: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_concedente_r: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_total_convenio_r: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    source_row_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    resource_name: Mapped[str] = mapped_column(Text)
    resource_url: Mapped[str] = mapped_column(Text)
    source_last_modified: Mapped[str | None] = mapped_column(String(100))
    downloaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sha256: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    error_message: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("resource_id", "sha256", name="uq_snapshot_resource_hash"),)


class RawBase:
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("source_snapshots.id"))
    source_resource_id: Mapped[str] = mapped_column(String(36))
    source_file: Mapped[str] = mapped_column(Text)
    source_row_number: Mapped[int] = mapped_column(Integer)
    source_last_modified: Mapped[str | None] = mapped_column(String(100))
    source_row_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ArrecadacaoRaw(RawBase, Base):
    __tablename__ = "arrecadacao_raw"
    uo: Mapped[str | None] = mapped_column(String(30))
    tipo_siafi: Mapped[str | None] = mapped_column(String(40))
    no_siafi: Mapped[str] = mapped_column(String(30), index=True)
    ano_exercicio_receita: Mapped[int | None] = mapped_column(Integer)
    tipo_de_receita: Mapped[str | None] = mapped_column(String(100))
    fonte: Mapped[str | None] = mapped_column(String(100))
    receita_arrecadada_r: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    data_da_arrecadacao: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("snapshot_id", "source_row_number", name="uq_arr_snapshot_row"),
    )


class ExecucaoRaw(RawBase, Base):
    __tablename__ = "execucao_raw"
    uo: Mapped[str | None] = mapped_column(String(30))
    tipo_siafi: Mapped[str | None] = mapped_column(String(40))
    no_siafi: Mapped[str] = mapped_column(String(30), index=True)
    ano_empenho: Mapped[int | None] = mapped_column(Integer, index=True)
    no_empenho: Mapped[str | None] = mapped_column(String(30), index=True)
    ue: Mapped[str | None] = mapped_column(String(30), index=True)
    data_empenho: Mapped[date | None] = mapped_column(Date)
    cnpj_cpf_credor: Mapped[str | None] = mapped_column(String(30), index=True)
    razao_social_credor: Mapped[str | None] = mapped_column(Text)
    valor_empenhado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_liquidado: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tipo_registro: Mapped[str] = mapped_column(String(30))
    __table_args__ = (
        UniqueConstraint("snapshot_id", "source_row_number", name="uq_exe_snapshot_row"),
    )


class ControleInterno(Base):
    __tablename__ = "controles_internos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_siafi: Mapped[str] = mapped_column(String(30), index=True)
    tipo: Mapped[str] = mapped_column(String(80))
    descricao: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConsultaAuditoria(Base):
    __tablename__ = "consultas_auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    ip: Mapped[str | None] = mapped_column(String(64))
    acao: Mapped[str] = mapped_column(String(80))
    codigo_siafi: Mapped[str | None] = mapped_column(String(30))
    intencao: Mapped[str | None] = mapped_column(String(80))
    resultado: Mapped[str | None] = mapped_column(Text)
    permitido: Mapped[bool] = mapped_column(Boolean)
    provedor_ia: Mapped[str | None] = mapped_column(String(30))
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    erro: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str | None] = mapped_column(String(20))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    siafi: Mapped[str | None] = mapped_column(String(30))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


Index(
    "ix_execucao_logical",
    ExecucaoRaw.no_siafi,
    ExecucaoRaw.ano_empenho,
    ExecucaoRaw.ue,
    ExecucaoRaw.no_empenho,
)
