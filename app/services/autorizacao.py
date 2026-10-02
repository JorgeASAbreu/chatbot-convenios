from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Convenio, Perfil, Usuario, UsuarioUnidade


def pode_consultar(db: Session, usuario: Usuario, convenio: Convenio) -> bool:
    """A autorização é aplicada no serviço para não depender da tela Streamlit."""
    if usuario.perfil in (Perfil.DF.value, Perfil.ADMIN.value):
        return True
    unit_ids = select(UsuarioUnidade.unidade_id).where(UsuarioUnidade.usuario_id == usuario.id)
    # UO do convênio é comparada ao código da unidade numa consulta explícita na camada de domínio.
    from app.db.models import Unidade

    return (
        db.scalar(
            select(Unidade.id).where(
                Unidade.id.in_(unit_ids), Unidade.codigo == convenio.unidade_orcamentaria
            )
        )
        is not None
    )
