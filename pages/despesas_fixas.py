import os
import uuid
import pandas as pd
import streamlit as st
from streamlit_tags import st_tags, st_tags_sidebar

BKP_PATH = "bkp/despesa_fixa.csv"

st.set_page_config(page_title="Despesas Fixas", layout="wide")
st.title("Despesas Fixas")

# lista base
if "keywords" not in st.session_state:
    st.session_state["keywords"] = [
        "Financiamento", "Internet", "Psicologa Sami", "Psicologa Mi", "Faculdade", "Havan"
    ]

# ---------- Utils ----------
def format_brl(value) -> str:
    try:
        x = float(value)
        if pd.isna(x):
            x = 0.0
    except Exception:
        x = 0.0

    s = f"{x:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def load_despesa_fixa() -> pd.DataFrame:
    os.makedirs("bkp", exist_ok=True)

    if not os.path.exists(BKP_PATH):
        return pd.DataFrame(columns=["ID", "Tipo", "Valor", ])

    df = pd.read_csv(BKP_PATH)

    # garante colunas
    if "ID" not in df.columns:
        df.insert(0, "ID", [str(uuid.uuid4()) for _ in range(len(df))])

    df["Tipo"] = df.get("Tipo", "Reembolso").fillna("Reembolso")
    df["Valor"] = pd.to_numeric(df.get("Valor"), errors="coerce").fillna(0.0)
    return df

def save_despesa_fixa(df: pd.DataFrame):
    os.makedirs("bkp", exist_ok=True)
    df.to_csv(BKP_PATH, index=False)

# ---------- Load ----------
df = load_despesa_fixa()

# ---------- Sidebar: filtros ----------


# ---------- Cadastro ----------
st.subheader("Adicionar receita")

col1, col2 = st.columns([2, 1])
    
with st.form("form_despesa"):
  # TAGS (seleção única)
  keyword = col1.pills(
      "Despesa (tag)",
      options=st.session_state["keywords"],
      selection_mode="single",
  )

  nova_tag = col1.text_input("Adicionar nova tag (opcional)", placeholder="Ex.: Mercado, Farmácia...")
    
  valor = col2.number_input("Valor", min_value=0.0, step=10.0, format="%.2f")

  submitted = st.form_submit_button("Adicionar")

if submitted:
    # se digitou uma nova tag, ela vira a keyword e entra na lista
    if nova_tag.strip():
        keyword = nova_tag.strip()
        if keyword not in st.session_state["keywords"]:
            st.session_state["keywords"].append(keyword)

    if not keyword:
        st.error("Selecione uma tag ou digite uma nova.")
        st.stop()

    st.success(f"Salvo: {keyword} — {valor:.2f}")
    rows = []

    rows.append({
          "ID": str(uuid.uuid4()),
          "Tipo": keyword,
          "Valor": float(valor),
      })

    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    save_despesa_fixa(df)
    st.success(f"Despesa Fixa Adicionada.")
    st.rerun()

df_view = df.copy()

# ---------- Tabela de lançamentos (editável) ----------
st.subheader("Lançamentos")

if df_view.empty:
    st.info("Nada para mostrar com os filtros atuais.")
else:
    # Mostra uma tabela editável pra marcar "Recebido"
    df_edit = df_view.copy()
    
    df_edit["Valor"] = df_edit["Valor"].apply(format_brl)

    edited = st.data_editor(
        df_edit[[ "Tipo", "Valor"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            # "ID": st.column_config.TextColumn("ID", disabled=True),
            "Tipo": st.column_config.TextColumn("Tipo", disabled=True),
            "Valor": st.column_config.NumberColumn("Valor", format="%.2f", disabled=True),
        },
        disabled=["Tipo","Valor"],  # deixa só Recebido/Obs editáveis
        key="editor_despesa_fixa",
    )

    colS1, colS2 = st.columns([1, 2])

    with colS2:
        st.download_button(
            "Baixar despesa_fixa.csv",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="despesa_fixa.csv",
            mime="text/csv",
        )
