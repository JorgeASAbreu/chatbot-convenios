import streamlit as st
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import ConsultaAuditoria, LlmUsage, Perfil, Usuario
from app.db.session import SessionLocal
from app.services.auth import AuthService
from app.services.chatbot import ChatService
from app.services.sync_dados_mg import DadosMGSyncService

st.set_page_config(page_title="Chatbot de Convênios — PMMG", layout="wide")


def login() -> Usuario | None:
    if "user_id" in st.session_state:
        with SessionLocal() as db:
            return db.get(Usuario, st.session_state.user_id)
    st.title("Chatbot de Consulta de Convênios")
    st.caption("POLÍCIA MILITAR DE MINAS GERAIS · DIRETORIA DE FINANÇAS · Subseção de Convênios")
    with st.form("login"):
        user, password = st.text_input("Usuário"), st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            with SessionLocal() as db:
                found = AuthService(db).authenticate(user, password)
                if found:
                    st.session_state.user_id = found.id
                    st.rerun()
                st.error("Credenciais inválidas.")
    return None


def side(user: Usuario) -> str:
    with st.sidebar:
        if __import__("pathlib").Path("assets/escudo_pmmg.png").exists():
            st.image("assets/escudo_pmmg.png", width=120)
        st.markdown(
            "**POLÍCIA MILITAR DE MINAS GERAIS**\n\nDIRETORIA DE FINANÇAS\n\nSubseção de Convênios"
        )
        st.caption(
            f"Usuário: {user.nome}\n\nPerfil: {user.perfil}\n\nIA: {get_settings().llm_provider}"
        )
        pages = ["Chat", "Detalhes"] + (
            ["Administração", "Atualização da Base", "Uso de IA", "Auditoria"]
            if user.perfil in (Perfil.DF.value, Perfil.ADMIN.value)
            else []
        )
        page = st.radio("Página", pages)
        if st.button("Sair"):
            st.session_state.clear()
            st.rerun()
        return page


def audit(db, user, action, siafi=None, result="ok"):
    db.add(
        ConsultaAuditoria(
            usuario_id=user.id,
            acao=action,
            codigo_siafi=siafi,
            resultado=result,
            permitido=True,
            provedor_ia=get_settings().llm_provider,
        )
    )
    db.commit()


def chat(user: Usuario):
    st.header("Chatbot de Convênios")
    if "messages" not in st.session_state:
        st.session_state.messages = [
            (
                "assistant",
                "Olá! Sou o Assistente de Convênios da Diretoria de Finanças da PMMG.\n\n"
                "Informe o número SIAFI ou o nome do concedente.",
            )
        ]
    for role, msg in st.session_state.messages:
        st.chat_message(role).write(msg)
    if question := st.chat_input("Ex.: 9282916, quanto foi pago?"):
        st.session_state.messages.append(("user", question))
        st.chat_message("user").write(question)
        with SessionLocal() as db:
            response = ChatService(db, user).respond(question, st.session_state.get("siafi_ativo"))
            audit(db, user, "CHAT", response.siafi, response.texto)
        if response.siafi:
            st.session_state.siafi_ativo = response.siafi
        st.session_state.messages.append(("assistant", response.texto))
        st.chat_message("assistant").write(response.texto)
        if response.warning:
            st.warning(response.warning)
        if response.detalhes:
            with st.expander("Ver detalhes"):
                st.json(response.detalhes, expanded=False)


def admin_page(user: Usuario, page: str):
    with SessionLocal() as db:
        if page == "Atualização da Base":
            st.header("Atualização da Base")
            if st.button("Atualizar Base", type="primary"):
                try:
                    snapshots = DadosMGSyncService(db, get_settings().dados_mg_proxy).sync_all()
                    audit(db, user, "SYNC", result=f"{len(snapshots)} recursos")
                    st.success("Sincronização concluída.")
                except Exception as e:
                    st.error(f"Falha na sincronização: {e}")
        elif page == "Auditoria":
            st.header("Auditoria")
            st.dataframe(
                [
                    {
                        "quando": x.created_at,
                        "ação": x.acao,
                        "siafi": x.codigo_siafi,
                        "resultado": x.resultado,
                    }
                    for x in db.scalars(
                        select(ConsultaAuditoria)
                        .order_by(ConsultaAuditoria.created_at.desc())
                        .limit(500)
                    )
                ]
            )
        elif page == "Uso de IA":
            st.info("Uso de IA é opcional. O provedor atual é " + get_settings().llm_provider + ".")
            st.dataframe(
                [
                    {
                        "quando": x.timestamp,
                        "provider": x.provider,
                        "model": x.model,
                        "operation": x.operation,
                        "input_tokens": x.input_tokens,
                        "output_tokens": x.output_tokens,
                        "estimated_cost": x.estimated_cost,
                        "latency_ms": x.latency_ms,
                        "success": x.success,
                        "error": x.error,
                        "user_id": x.user_id,
                        "siafi": x.siafi,
                    }
                    for x in db.scalars(select(LlmUsage).order_by(LlmUsage.id.desc()).limit(20))
                ]
            )
        else:
            st.header(page)
            st.info(
                "Administração de usuários e controles internos será efetuada diretamente "
                "no banco nesta homologação."
            )


user = login()
if user:
    page = side(user)
    if page == "Chat":
        chat(user)
    elif page == "Detalhes":
        st.header("Detalhes do Convênio")
        st.write("Consulte um convênio no Chat para estabelecer o contexto.")
    else:
        admin_page(user, page)
