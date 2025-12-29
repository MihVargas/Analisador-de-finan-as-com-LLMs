import os
import uuid
import pandas as pd
import streamlit as st
from datetime import date
import calendar
from datetime import date

BKP_PATH = "bkp/receitas.csv"

st.set_page_config(page_title="Receitas", layout="wide")
st.title("Receitas (a receber)")


def default_dia_10() -> date:
    hoje = date.today()
    if hoje.day > 10:
        # dia 10 do próximo mês
        y, m = hoje.year, hoje.month + 1
        if m == 13:
            y, m = y + 1, 1
        return date(y, m, 10)
    # dia 10 do mês vigente
    return date(hoje.year, hoje.month, 10)

def add_months_keep_day(d: date, months: int) -> date:
    # soma meses mantendo o dia (ajusta se estourar o fim do mês)
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)

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

def load_receitas() -> pd.DataFrame:
    os.makedirs("bkp", exist_ok=True)

    if not os.path.exists(BKP_PATH):
        return pd.DataFrame(columns=["ID", "Tipo", "Pessoa", "Valor", "Vezes", "Data", "Recebido", "Observacao"])

    df = pd.read_csv(BKP_PATH)

    # garante colunas
    if "ID" not in df.columns:
        df.insert(0, "ID", [str(uuid.uuid4()) for _ in range(len(df))])

    if "Recebido" not in df.columns:
        # se existia Status antigo, tenta converter
        if "Status" in df.columns:
            df["Recebido"] = df["Status"].astype(str).str.strip().str.upper().eq("RECEBIDO")
            df = df.drop(columns=["Status"])
        else:
            df["Recebido"] = False

    if "Observacao" not in df.columns:
        df["Observacao"] = ""

    df["Tipo"] = df.get("Tipo", "Reembolso").fillna("Reembolso")
    df["Pessoa"] = df.get("Pessoa", "").fillna("")
    df["Valor"] = pd.to_numeric(df.get("Valor"), errors="coerce").fillna(0.0)
    df["Vezes"] = pd.to_numeric(df.get("Vezes"), errors="coerce").fillna(1).astype(int)
    df["Data"] = pd.to_datetime(df.get("Data"), errors="coerce").dt.date
    df["Recebido"] = df["Recebido"].fillna(False).astype(bool)
    df["Observacao"] = df["Observacao"].fillna("")

    if "ParcelaAtual" not in df.columns:
        df["ParcelaAtual"] = pd.NA
    if "ParcelaTotal" not in df.columns:
        df["ParcelaTotal"] = pd.NA

    df["ParcelaAtual"] = pd.to_numeric(df["ParcelaAtual"], errors="coerce")
    df["ParcelaTotal"] = pd.to_numeric(df["ParcelaTotal"], errors="coerce")


    return df

def save_receitas(df: pd.DataFrame):
    os.makedirs("bkp", exist_ok=True)
    df.to_csv(BKP_PATH, index=False)

# ---------- Load ----------
df = load_receitas()

# ---------- Sidebar: filtros ----------
st.sidebar.header("Filtros")

meses = sorted(df["MesRef"].dropna().unique().tolist())

def fmt_mes(p):
    # p é Period('2025-01', 'M')
    return p.strftime("%m/%Y")  # ex: 01/2025

if meses:
    print("ok")
    mes_ref = st.sidebar.selectbox(
        "Mês de referência",
        options=meses,
        index=len(meses) - 1
    )
else:
    st.sidebar.warning("Não encontrei datas válidas no arquivo.")
    mes_ref = None

pessoas = sorted([p for p in df["Pessoa"].dropna().unique().tolist() if str(p).strip()]) if not df.empty else []
pessoas_opts = ["Todas"] + pessoas

pessoa_sel = st.sidebar.segmented_control(
    "Pessoa",
    options=pessoas_opts if pessoas_opts else ["Todas"],
    default="Todas",
)

tipo_sel = st.sidebar.pills(
    "Tipo",
    options=["Reembolso", "Salário"],
    default=["Reembolso", "Salário"],
    selection_mode="multi",
)

recebido_sel = st.sidebar.pills(
    "Mostrar",
    options=["Pendentes", "Recebidos"],
    default=["Pendentes"],
    selection_mode="multi",
)

# ---------- Cadastro ----------
st.subheader("Adicionar receita")

with st.form("form_receita", clear_on_submit=True):
    col1, col2, col3, col4 = st.columns([1.2, 1.6, 1, 1.2])

    tipo = col1.selectbox("Tipo", ["Reembolso", "Salário"])
    pessoa = col2.text_input("Pessoa (tag)", placeholder="Ex.: Pessoa 1 / Fulano / Empresa")
    valor = col3.number_input("Valor", min_value=0.0, step=10.0, format="%.2f")
    vezes = col4.number_input("Quantas vezes", min_value=1, step=1, value=1)

    col5, col6 = st.columns([1, 1])
    data_lanc = col5.date_input("Data", value=default_dia_10())
    recebido = col6.checkbox("Já foi recebido?", value=False)

    observacao = st.text_input("Observação (opcional)", placeholder="Ex.: pix combinado até dia 10")

    submitted = st.form_submit_button("Adicionar")

if submitted:
    pessoa_norm = pessoa.strip() if pessoa else ""
    obs_norm = observacao.strip() if observacao else ""

    rows = []
    n = int(vezes)

    for k in range(n):
        rows.append({
            "ID": str(uuid.uuid4()),
            "Tipo": tipo,
            "Pessoa": pessoa_norm,
            "Valor": float(valor),
            "Vezes": n,  # mantém o total digitado
            "Data": add_months_keep_day(data_lanc, k),  # 0, +1 mês, +2 meses...
            "Recebido": bool(recebido),
            "Observacao": obs_norm,
            "ParcelaAtual": (k + 1) if n > 1 else pd.NA,
            "ParcelaTotal": n if n > 1 else pd.NA,
        })

    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["MesRef"] = df["Data"].dt.to_period("M")
    save_receitas(df)
    st.success(f"Receita adicionada ({n}x).")
    st.rerun()

# ---------- Aplicar filtros ----------


# df_view = df.copy()
df_view = df.copy()
if mes_ref is not None:
    df_view = df_view[df_view["MesRef"] == mes_ref]


if tipo_sel:
    df_view = df_view[df_view["Tipo"].isin(tipo_sel)]

if pessoa_sel and pessoa_sel != "Todas":
    df_view = df_view[df_view["Pessoa"] == pessoa_sel]

# filtro recebido/pendente
show_pend = "Pendentes" in recebido_sel
show_rec  = "Recebidos" in recebido_sel

if show_pend and not show_rec:
    df_view = df_view[df_view["Recebido"] == False]
elif show_rec and not show_pend:
    df_view = df_view[df_view["Recebido"] == True]
# se os dois selecionados, não filtra

# ---------- Resumo por pessoa (pendente) ----------
st.subheader("Resumo por pessoa (pendente)")

df_pend_ree = df[(df["Tipo"] == "Reembolso") & (df["Recebido"] == False)].copy()

df_pend_sal = df[(df["Tipo"] == "Salário") & (df["Recebido"] == False)].copy()

if mes_ref is not None:
    df_pend_ree = df_pend_ree[df_pend_ree["MesRef"] == mes_ref]
    df_pend_sal = df_pend_sal[df_pend_sal["MesRef"] == mes_ref]


if df_pend_ree.empty and df_pend_sal.empty:
    st.info("Sem reembolsos pendentes.")
else:
    resumo = (
        df_pend_ree.groupby("Pessoa", dropna=False)["Valor"]
        .sum()
        .reset_index()
        .sort_values("Valor", ascending=False)
    )
    resumo2 = (
        df_pend_sal.groupby("Pessoa", dropna=False)["Valor"]
        .sum()
        .reset_index()
        .sort_values("Valor", ascending=False)
    )

    colA, colB = st.columns([1, 2])

    with colA:
        total_pendente = df_pend_ree["Valor"].sum()
        st.metric("Total pendente (reembolsos)", format_brl(total_pendente))

        total_salario = df_pend_sal["Valor"].sum()
        st.metric("Total pendente (salários)", format_brl(total_salario))

    with colB:
        resumo_show = resumo.copy()
        resumo_show["Valor"] = resumo_show["Valor"].apply(format_brl)
        resumo_show = resumo_show.rename(columns={"Valor": "Total pendente"})
        st.dataframe(resumo_show, use_container_width=True, hide_index=True)

        resumo_show = resumo2.copy()
        resumo_show["Valor"] = resumo_show["Valor"].apply(format_brl)
        resumo_show = resumo_show.rename(columns={"Valor": "Total pendente"})
        st.dataframe(resumo_show, use_container_width=True, hide_index=True)

# ---------- Tabela de lançamentos (editável) ----------
st.subheader("Lançamentos")

if df_view.empty:
    st.info("Nada para mostrar com os filtros atuais.")
else:

    df_view = df_view.copy()
    if mes_ref is not None:
        df_view = df_view[df_view["MesRef"] == mes_ref]

    df_view["Parcela"] = df_view.apply(
        lambda r: f"{int(r['ParcelaAtual']):02d}/{int(r['ParcelaTotal']):02d}"
        if pd.notna(r.get("ParcelaTotal")) else "",
        axis=1
    )
    # Mostra uma tabela editável pra marcar "Recebido"
    df_edit = df_view.copy()
    
    df_edit["Valor"] = df_edit["Valor"].apply(format_brl)

    edited = st.data_editor(
        df_edit[["Data", "Tipo", "Pessoa", "Valor", "ParcelaAtual", "Recebido", "Observacao"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            # "ID": st.column_config.TextColumn("ID", disabled=True),
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", disabled=True),
            "Tipo": st.column_config.TextColumn("Tipo", disabled=True),
            "Pessoa": st.column_config.TextColumn("Pessoa", disabled=True),
            "Valor": st.column_config.NumberColumn("Valor", format="%.2f", disabled=True),
            "ParcelaAtual": st.column_config.TextColumn("Parcela Atual"),
            "Recebido": st.column_config.CheckboxColumn("Recebido"),
            "Observacao": st.column_config.TextColumn("Obs"),  # se quiser travar, coloca disabled=True
        },
        disabled=["Data", "Tipo", "Pessoa", "Valor", "ParcelaAtual"],  # deixa só Recebido/Obs editáveis
        key="editor_receitas",
    )

    colS1, colS2 = st.columns([1, 2])
    with colS1:
        if st.button("Salvar alterações", type="primary"):
            # aplica alterações no df original pelo ID
            df_new = df.copy()
            upd = edited[["ID", "Recebido", "Observacao"]].copy()

            df_new = df_new.merge(upd, on="ID", how="left", suffixes=("", "_new"))
            df_new["Recebido"] = df_new["Recebido_new"].fillna(df_new["Recebido"]).astype(bool)
            df_new["Observacao"] = df_new["Observacao_new"].fillna(df_new["Observacao"])
            df_new = df_new.drop(columns=["Recebido_new", "Observacao_new"])

            save_receitas(df_new)
            st.success("Alterações salvas!")
            st.rerun()

    with colS2:
        st.download_button(
            "Baixar receitas.csv",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="receitas.csv",
            mime="text/csv",
        )
