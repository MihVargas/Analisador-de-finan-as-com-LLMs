import streamlit as st
from streamlit_extras.badges import badge
from datetime import date

def render_sidebar():
    # estados padrão
    st.session_state.setdefault("exp_processamento", True)
    st.session_state.setdefault("exp_filtros", False)
    st.session_state.setdefault("rodou", False)

    st.sidebar.header("Configurações")

    # =========================
    # Expander: Processamento
    # =========================
    with st.sidebar.expander("⚙️ Processamento", expanded=st.session_state["exp_processamento"]):

        col1, col2 = st.columns(2)
        mes = col1.selectbox(
            "Mês",
            options=list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda m: f"{m:02d}",
        )

        ano = col2.number_input(
            "Ano",
            min_value=2020,
            max_value=2100,
            value=date.today().year,
            step=1,
        )

        mes_ref = f"{ano}-{mes:02d}" 
        
        fonte = st.radio(
            "Fonte dos dados",
            ["Upload (CSV do cartão)", "Ler do backup (bkp/finances_cartao.csv)"],
            key="fonte",
        )

        uploaded = None
        if fonte == "Upload (CSV do cartão)":
            uploaded = st.file_uploader("Envie o CSV do cartão", type=["csv"], key="uploaded")

        acao = st.selectbox(
            "O que executar?",
            [
                "Processar tudo (recomendado)",
                "Só ler CSV",
                "Ler CSV + parcelas",
                "Ler CSV + parcelas + categorizar (LLM)",
            ],
            key="acao",
        )

        salvar_csv = st.checkbox("Salvar CSV em bkp/finances_cartao.csv", value=True, key="salvar_csv")

        rodar = st.button("Executar", key="executar")

    # =========================
    # Expander: Filtros
    # =========================
    with st.sidebar.expander("🔎 Filtros", expanded=st.session_state["exp_filtros"]):
        # aqui você NÃO monta os filtros ainda (isso fica em ui_analysis),
        # mas você pode colocar um placeholder/aviso:
        if not st.session_state.get("rodou"):
            st.caption("Processe ou carregue um arquivo para liberar os filtros.")
        # (os filtros reais você constrói no ui_analysis com df disponível)

    # Quando clica executar, troca os expanders
    if rodar:
        st.session_state["rodou"] = True
        st.session_state["exp_processamento"] = False
        st.session_state["exp_filtros"] = True

    # def example_buymeacoffee():
    #     badge(type="buymeacoffee", name="mihvargasw", url="https://buymeacoffee.com/mihvargasw")


    # example_buymeacoffee()

    return {
        "fonte": st.session_state["fonte"],
        "uploaded": uploaded,
        "acao": st.session_state["acao"],
        "salvar_csv": st.session_state["salvar_csv"],
        "rodar": rodar,
        "mes_ref": mes_ref,
    }


