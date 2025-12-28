import streamlit as st
from agente import AgenteCartao
from ui_sidebar import render_sidebar
from ui_analysis import carregar_backup, processar_upload, render_result

st.set_page_config(page_title="Analisador Cartão", layout="wide")
st.title("Analisador de Fatura do Cartão")

agente = AgenteCartao()

ui = render_sidebar()

# modo backup
if ui["fonte"].startswith("Ler do backup"):
    df = carregar_backup()
    render_result(df)
    st.stop()

# modo upload
if ui["uploaded"] is None:
    st.info("Faça o upload de um CSV na barra lateral para começar.")
    st.stop()

if ui["rodar"]:
    df = processar_upload(agente, ui["uploaded"], ui["acao"], ui["salvar_csv"])
    render_result(df)
else:
    st.info("Escolha as opções na barra lateral e clique em Executar.")

