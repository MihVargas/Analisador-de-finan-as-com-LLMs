import pandas as pd
from dotenv import load_dotenv, find_dotenv
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
import time
import re

def _parse_valor(x):
    s = str(x).strip()
    s = s.replace("R$", "").replace(" ", "")
    # remove separador de milhar
    return pd.to_numeric(s, errors="coerce")


def ler_csv_cartao(path: str) -> pd.DataFrame:
    # 1) tenta ler com separadores comuns
    try:
        df = pd.read_csv(path, sep=",", encoding="utf-8")
    except Exception:
        try:
            df = pd.read_csv(path, sep=";", encoding="utf-8")
        except Exception:
            df = pd.read_csv(path, sep=",", encoding="latin-1")

    # 2) normaliza nomes de colunas (caso venham diferentes)
    df.columns = [c.strip().lower() for c in df.columns]

    # tenta mapear colunas esperadas
    # você disse: data,lançamento,valor
    col_data = next((c for c in df.columns if "data" in c), None)
    col_lanc = next((c for c in df.columns if "lan" in c or "descr" in c), None)
    col_val  = next((c for c in df.columns if "valor" in c or "amount" in c), None)

    if not all([col_data, col_lanc, col_val]):
        raise ValueError(f"Não achei as colunas. Encontrei: {df.columns.tolist()}")

    df = df[[col_data, col_lanc, col_val]].copy()
    df.columns = ["Data", "Lançamento", "Valor"]

    # 3) converte data
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date

    # 4) converte valor (aceita '72,39' e '72.39' e também com R$)

    df["Valor"] = df["Valor"].apply(_parse_valor)

    # 5) limpeza básica do texto
    df["Lançamento"] = df["Lançamento"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

    # remove linhas ruins
    df = df.dropna(subset=["Data", "Lançamento", "Valor"]).reset_index(drop=True)

    return df

# =========================
# LLM (Batch)
# =========================
load_dotenv(find_dotenv())

template = """
Você é um analista de dados em um projeto de limpeza de lançamentos de CARTÃO DE CRÉDITO (pessoa física).
Sua tarefa é escolher UMA categoria para o lançamento com base no estabelecimento/descrição.

Escolha exatamente UMA das categorias abaixo:
- Moradia
- Contas da casa
- Internet & Telefone
- Streaming/Assinaturas
- Carro
- Transporte
- Mercado
- Delivery/Restaurantes
- Saúde
- Educação
- Pets
- Beleza
- Compras & Casa
- Lazer
- Bancos & Tarifas
- Outros

REGRAS IMPORTANTES:
1) No cartão de crédito, Valor NEGATIVO normalmente significa CRÉDITO/ESTORNO/REEMBOLSO/DESCONTO.
   Mesmo assim, a CATEGORIA deve refletir o tipo de estabelecimento.
2) "Bancos & Tarifas" apenas para anuidade, juros, multa, IOF, encargos, rotativo, parcelamento da fatura, tarifa do cartão.
3) Se tiver parcela tipo "01/06", isso NÃO muda a categoria.
4) Se estiver ambíguo, use "Compras & Casa" como padrão; se realmente não der, use "Outros".

Agora classifique este lançamento:
{text}

Responda APENAS com o nome exato da categoria (uma linha).
""".strip()

prompt = PromptTemplate.from_template(template)
chat = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0,
    timeout=60,
    max_retries=5,
)
chain = prompt | chat | StrOutputParser()

# =========================
# Execução
# =========================
df = ler_csv_cartao("faturas/fatura-945219970 copy.csv")

parc_re = re.compile(r"(\d{2})/(\d{2})")

def extrair_parcela(lancamento: str):
    if pd.isna(lancamento):
        return pd.NA, pd.NA

    s = str(lancamento)
    matches = parc_re.findall(s)  # lista de tuplas [('09','12'), ('14','10'), ...]

    # pega o último match válido (mais comum no cartão)
    for a, t in reversed(matches):
        atual = int(a)
        total = int(t)

        # validação: parcela faz sentido
        if total >= 2 and 1 <= atual <= total:
            return atual, total

    return pd.NA, pd.NA

df[["ParcelaAtual", "ParcelaTotal"]] = df["Lançamento"].apply(
    lambda x: pd.Series(extrair_parcela(x))
)

df["Parcela"] = df.apply(
    lambda r: f"{int(r['ParcelaAtual']):02d}/{int(r['ParcelaTotal']):02d}"
    if pd.notna(r["ParcelaTotal"]) else "",
    axis=1
)

df["Lancamento_Limpo"] = df["Lançamento"].str.replace(parc_re, " ", regex=True)\
                                        .str.replace(r"\s+", " ", regex=True)\
                                        .str.strip()


# Deduplica (menos chamadas)
texts = df["Lancamento_Limpo"].astype(str).fillna("")
texts_unicos = texts.unique().tolist()

# Batch controlado para não estourar RPM
# Se ainda bater rate limit, aumente o sleep ou diminua o max_concurrency (já está 1)
categorias_unicas = []
BATCH_SIZE = 20  # <=30 por minuto costuma ser mais seguro, dependendo do tempo de resposta

for i in range(0, len(texts_unicos), BATCH_SIZE):
    chunk = texts_unicos[i:i + BATCH_SIZE]
    resps = chain.batch(chunk, config={"max_concurrency": 1})

    # limpa espaços/linhas extras
    resps = [r.strip() for r in resps]

    categorias_unicas.extend(resps)

    # respeita RPM do tier on_demand (30 RPM). Ajuste se necessário.
    time.sleep(3)

mapa_texto_para_cat = dict(zip(texts_unicos, categorias_unicas))
df["Categoria"] = texts.map(mapa_texto_para_cat)

df.to_csv("finances_cartao.csv", index=False)
print("OK: arquivo 'finances_cartao.csv' gerado.")