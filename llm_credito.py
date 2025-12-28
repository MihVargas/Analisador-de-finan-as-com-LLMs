import os
import time
from datetime import datetime

import ofxparse
import pandas as pd
from dotenv import load_dotenv, find_dotenv
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq

# =========================
# 1) Ler extratos OFX -> DataFrame
# =========================

EXTRATOS_DIR = "extratos"

rows = []
for nome_arquivo in os.listdir(EXTRATOS_DIR):
    caminho = os.path.join(EXTRATOS_DIR, nome_arquivo)

    # opcional: filtra só arquivos OFX
    if not nome_arquivo.lower().endswith((".ofx", ".qfx")):
        continue

    with open(caminho, encoding="ISO-8859-1") as ofx_file:
        ofx = ofxparse.OfxParser.parse(ofx_file)

    for account in getattr(ofx, "accounts", []):
        st = getattr(account, "statement", None)
        if not st:
            continue

        for tr in getattr(st, "transactions", []):
            rows.append(
                {
                    "ID": tr.id,
                    "Data": tr.date.date(),  # já vira date()
                    "Valor": float(tr.amount),
                    "Descrição": (tr.memo or "").strip(),
                }
            )

df = pd.DataFrame(rows)

# Se não tiver nada, evita crash e avisa
if df.empty:
    raise RuntimeError(f"Nenhuma transação encontrada em '{EXTRATOS_DIR}'.")

# Se existir ID repetido, melhor não usar como index único.
# Aqui mantemos ID como coluna e criamos um índice padrão.
# Se você realmente precisa index por ID, dá pra usar set_index depois de tratar duplicados.
# df = df.set_index("ID")

# =========================
# 2) LLM: Categorizar descrições (com menos chamadas e sem estourar RPM)
# =========================

# Carrega .env (GROQ_API_KEY=...)
load_dotenv(find_dotenv())

template = """
Você é um analista de dados trabalhando em um projeto de limpeza de dados.
Seu trabalho é escolher uma categoria adequada para cada lançamento financeiro.

Todos são transações financeiras de uma pessoa física.

Escolha UMA dentre as seguintes categorias:
- Alimentação
- Receitas
- Saúde
- Mercado
- Educação
- Compras
- Transporte
- Investimento
- Transferências para terceiros
- Telefone
- Moradia

Escolha a categoria deste item:
{text}

Responda apenas com a categoria.
""".strip()

prompt = PromptTemplate.from_template(template)

# Use um modelo mais leve para evitar rate-limit com muitas chamadas
chat = ChatGroq(model="llama-3.1-8b-instant")
chain = prompt | chat | StrOutputParser()

# Deduplica descrições para reduzir MUITO as chamadas
descricoes = df["Descrição"].astype(str).fillna("")
descricoes_unicas = descricoes.unique().tolist()

def classify_with_retry(text: str, max_retries: int = 6) -> str:
    """Classifica uma descrição com retry/backoff simples em caso de 429."""
    delay = 1.0
    last_err = None

    for _ in range(max_retries):
        try:
            # invoke espera dict para preencher {text}
            return chain.invoke({"text": text}).strip()
        except Exception as e:
            msg = str(e).lower()
            if ("rate limit" in msg) or ("429" in msg) or ("rate_limit" in msg) or \
            ("connection error" in msg) or ("getaddrinfo" in msg) or ("connecterror" in msg):
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
                last_err = e
                continue
            raise


    raise RuntimeError(f"Falhou após {max_retries} tentativas (rate limit). Último erro: {last_err}")



# Classifica as descrições únicas
# (Se quiser tentar batch, dá pra usar batch com max_concurrency=1, mas o loop com retry é mais robusto.)
mapa_desc_para_cat = {}
for d in descricoes_unicas:
    mapa_desc_para_cat[d] = classify_with_retry(d)

df["Categoria"] = descricoes.map(mapa_desc_para_cat)

# =========================
# 3) Filtrar e salvar
# =========================

df = df[df["Data"] >= datetime(2024, 3, 1).date()]

# Se você quiser index por ID e tiver certeza que não duplica:
# df = df.set_index("ID")

df.to_csv("finances.csv", index=False)
print("OK: arquivo 'finances.csv' gerado.")
