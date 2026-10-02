import unicodedata
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Convenio


def normalizar(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn"
    )


class ConvenioService:
    def __init__(self, db: Session):
        self.db = db

    def por_siafi(self, siafi: str) -> Convenio | None:
        return self.db.scalar(select(Convenio).where(Convenio.codigo_siafi == siafi))

    def por_concedente(self, consulta: str) -> list[Convenio]:
        # Preserva portabilidade; PostgreSQL pode receber índice unaccent posteriormente.
        return [
            c
            for c in self.db.scalars(select(Convenio)).all()
            if normalizar(consulta) in normalizar(c.concedente or "")
        ]

    @staticmethod
    def situacao(convenio: Convenio) -> tuple[str | None, bool]:
        encerrado = bool(convenio.termino_vigencia and convenio.termino_vigencia < date.today())
        return (
            "ENCERRADA" if encerrado else convenio.situacao_fonte,
            encerrado and (convenio.situacao_fonte or "").upper() == "VIGENTE",
        )
