import os
import streamlit as st
import pandas as pd
from streamlit_extras.metric_cards import style_metric_cards

BKP_PATH = "bkp/finances_cartao.csv"

def format_brl(value) -> str:
    """
    Formata número para Real brasileiro: R$ 7.299,66
    Aceita int/float/str; trata NaN como R$ 0,00.
    """
    try:
        x = float(value)
        if pd.isna(x):
            x = 0.0
    except Exception:
        x = 0.0

    s = f"{x:,.2f}"                 # 7,299.66 (padrão US)
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")  # 7.299,66
    return f"R$ {s}"


def carregar_backup():
    if not os.path.exists(BKP_PATH):
        st.warning("Ainda não existe backup em bkp/finances_cartao.csv. Faça um upload e processe primeiro.")
        st.stop()
    return pd.read_csv(BKP_PATH)


def render_total(df: pd.DataFrame):
    # garanta numérico
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    receita = 10000
    despesas_fixas = 4563

    valor_total = df["Valor"].sum().round(2)

    saldo_comprometido = receita - despesas_fixas - valor_total

    parcela_ending = df[
        (df["ParcelaAtual"].notna()) &
        (df["ParcelaTotal"].notna()) &
        (df["ParcelaAtual"] == df["ParcelaTotal"])
    ].shape[0]

    limite_gasto = (8000-valor_total).round(2)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Receita",  value=format_brl(receita))
    col2.metric("Despesas Fixas", value=format_brl(despesas_fixas))
    col3.metric("Saldo Comprometido", value=format_brl(saldo_comprometido))
    style_metric_cards()

def render_metrics(df: pd.DataFrame):
    # garanta numérico
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    valor_total = df["Valor"].sum().round(2)
    valor_reembolso = df[df["Valor"] < 0]["Valor"].sum().round(2)

    parcela_ending = df[
        (df["ParcelaAtual"].notna()) &
        (df["ParcelaTotal"].notna()) &
        (df["ParcelaAtual"] == df["ParcelaTotal"])
    ].shape[0]

    total_parcelas = df[df["ParcelaAtual"].notna()].shape[0]

    limite_gasto = (8000-valor_total).round(2)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total",  value=format_brl(valor_total), delta=format_brl(limite_gasto), help="Soma dos valores sem aplicar filtros")
    col2.metric("Reembolsos & Créditos", format_brl(valor_reembolso), help="Soma dos reembolsos e créditos")
    col3.metric("Parcelas encerrando", parcela_ending, help="Número de parcelas que estão na última parcela")
    col4.metric("Total parcelas", total_parcelas, help="Número total de lançamentos parcelados")
    style_metric_cards()

def render_metrics_grupado(df: pd.DataFrame):
    # garanta numérico
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    valor_total = df["Valor"].sum().round(2)
    valor_reembolso = df[df["Valor"] < 0]["Valor"].sum().round(2)

    parcela_ending = df[
        (df["ParcelaAtual"].notna()) &
        (df["ParcelaTotal"].notna()) &
        (df["ParcelaAtual"] == df["ParcelaTotal"])
    ].shape[0]

    total_parcelas = df[df["ParcelaAtual"].notna()].shape[0]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total",  value=format_brl(valor_total), help="Soma dos valores após filtros")
    col2.metric("Reembolsos & Créditos", format_brl(valor_reembolso), help="Soma dos reembolsos e créditos")
    col3.metric("Parcelas encerrando", parcela_ending, help="Número de parcelas que estão na última parcela")
    col4.metric("Total parcelas", total_parcelas, help="Número total de lançamentos parcelados")
    style_metric_cards()

def filtrar_pagamento_efetuado(df: pd.DataFrame) -> pd.DataFrame:
    # remove "PAGAMENTO EFETUADO" (robusto)
    if "Lancamento_Limpo" in df.columns:
        mask = df["Lancamento_Limpo"].astype(str).str.strip().str.upper() != "PAGAMENTO EFETUADO"
        return df[mask].copy()
    return df

def processar_upload(agente, uploaded, acao: str, salvar_csv: bool):
    progress = st.sidebar.progress(0)
    status = st.sidebar.empty()

    with st.spinner("Processando..."):
        status.write("📥 Lendo CSV do cartão...")
        progress.progress(15)
        df = agente.ler_csv_cartao(uploaded)

        if acao == "Só ler CSV":
            progress.progress(100)
            status.success("✅ Concluído.")
            return df

        status.write("🧾 Adicionando parcelas...")
        progress.progress(40)
        df = agente.adicionar_parcelas(df)

        # remove pagamento efetuado antes do LLM
        df = filtrar_pagamento_efetuado(df)

        if acao == "Ler CSV + parcelas":
            progress.progress(100)
            status.success("✅ Concluído.")
            return df

        status.write("🤖 Categorizando lançamentos via Groq...")
        progress.progress(70)

        def on_llm_progress(done: int, total: int):
            base = 70
            span = 20
            pct = base + int(span * (done / max(total, 1)))
            progress.progress(pct)
            status.write(f"🤖 Categorizando lançamentos via Groq... {done}/{total}")

        df = agente.categorizar_batch(df, on_progress=on_llm_progress)

        # regra final: valor negativo = reembolso/crédito
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")
        df.loc[df["Valor"] < 0, "Categoria"] = "Reembolsos & Créditos"

        if salvar_csv:
            status.write("💾 Salvando arquivo...")
            progress.progress(95)
            os.makedirs("bkp", exist_ok=True)
            df.to_csv(BKP_PATH, index=False)

        progress.progress(100)
        status.success("✅ Processamento concluído.")
        return df

def aplicar_filtros(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # garante tipos
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    if "Valor" in df.columns:
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    st.sidebar.subheader("Filtros")

    # Categoria (multi)
    categorias = sorted(df["Categoria"].dropna().unique().tolist()) if "Categoria" in df.columns else []
    cat_sel = st.sidebar.pills(
        "Categoria",
        options=categorias,
        default=categorias,          # seleciona todas por padrão
        selection_mode="multi",
    )

    # Parcelado?
    if "ParcelaTotal" in df.columns:
        so_parcelado = st.sidebar.checkbox("Somente parcelados", value=False)
    else:
        so_parcelado = False

    # Período
    if "Data" in df.columns and df["Data"].notna().any():
        data_min = df["Data"].min()
        data_max = df["Data"].max()
        intervalo = st.sidebar.date_input(
            "Período",
            value=(data_min.date(), data_max.date()),
            min_value=data_min.date(),
            max_value=data_max.date(),
        )
        if isinstance(intervalo, tuple) and len(intervalo) == 2:
            ini, fim = intervalo
            df = df[(df["Data"].dt.date >= ini) & (df["Data"].dt.date <= fim)]

    # Busca por texto
    if "Lancamento_Limpo" in df.columns:
        q = st.sidebar.text_input("Buscar no lançamento", "")
        if q.strip():
            df = df[df["Lancamento_Limpo"].astype(str).str.contains(q, case=False, na=False)]

    # Range de valor (opcional)
    if "Valor" in df.columns and df["Valor"].notna().any():
        vmin, vmax = float(df["Valor"].min()), float(df["Valor"].max())
        vr = st.sidebar.slider("Valor (range)", min_value=vmin, max_value=vmax, value=(vmin, vmax))
        df = df[(df["Valor"] >= vr[0]) & (df["Valor"] <= vr[1])]

    # aplica categoria
    if "Categoria" in df.columns and cat_sel:
        df = df[df["Categoria"].isin(cat_sel)]


    # aplica parcelado
    if so_parcelado and "ParcelaTotal" in df.columns:
        df = df[df["ParcelaTotal"].fillna(0).astype(int) > 1]

    return df


def render_result(df: pd.DataFrame):
    st.subheader("Original")
    render_total(df)


    st.subheader("Resultado")
    render_metrics(df)

    df_view = aplicar_filtros(df)

    st.subheader("Resultado Filtrado")
    render_metrics_grupado(df_view)

    df_show = df_view.copy()

    # Data dd/MM/yyyy
    df_show["Data"] = pd.to_datetime(df_show["Data"], errors="coerce").dt.strftime("%d/%m/%Y")

    # Valor em BRL
    df_show["Valor"] = df_show["Valor"].apply(format_brl)

    # Renomear coluna
    df_show = df_show.rename(columns={"Lancamento_Limpo": "Descrição"})

    # Selecionar e ordenar colunas (ajuste como quiser)
    cols = [c for c in ["Data", "Descrição", "Valor", "Parcela", "Categoria"] if c in df_show.columns]
    df_show = df_show[cols]

    st.dataframe(df_show.reset_index(drop=True), use_container_width=True, hide_index=True)

    # download do resultado
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV", data=csv_bytes, file_name="finances_cartao.csv", mime="text/csv")
