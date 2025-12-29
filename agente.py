import re
import time
from dataclasses import dataclass
from typing import Union, IO, Optional, List, Dict, Any

import pandas as pd
from dotenv import load_dotenv, find_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq

from typing import Callable, Optional

FileLike = Union[str, IO[bytes], IO[str]]  # path ou file object (ex.: UploadedFile)


@dataclass
class AgenteCartaoConfig:
    model: str = "llama-3.1-8b-instant"
    temperature: float = 0
    timeout: int = 60
    max_retries: int = 5

    batch_size: int = 20
    max_concurrency: int = 1
    sleep_seconds: float = 3.0  # para respeitar RPM no on_demand


class AgenteCartao:
    """
    Agente para:
      - ler CSV do cartão
      - extrair parcelas
      - limpar lançamento
      - categorizar via Groq (batch)
    """

    def __init__(self, config: Optional[AgenteCartaoConfig] = None):
        self.config = config or AgenteCartaoConfig()

        # carrega env (GROQ_API_KEY)
        load_dotenv(find_dotenv())

        self.parc_re = re.compile(r"(\d{2})/(\d{2})")

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
- Reembolsos & Créditos

REGRAS IMPORTANTES:
1) Drogasil, drograria, farmácia, Raia, Unimed, Uniodonto, OdontoPrev = "Saúde".
2) "Bancos & Tarifas" apenas para anuidade, juros, multa, IOF, encargos, rotativo, parcelamento da fatura, tarifa do cartão.
3) Se tiver parcela tipo "01/06", isso NÃO muda a categoria.
4) Se estiver ambíguo, use "Compras & Casa" como padrão; se realmente não der, use "Outros".
5) canva, globo, hbo, netflix, spotify, disney+, prime video, helphbomaxcomNew, MICROSOFT, vivo, apple = "Streaming/Assinaturas".
6) uber, 99, ifood, rappi = "Delivery/Restaurantes
7) Passei direto, asimov, Centro de Esp Itapetininga, são "Educação"
8) Mercado livre e suas variações é "Compras & Casa"
9) agro, petz e afins é "Pets"

Agora classifique este lançamento:
{text}

Responda APENAS com o nome exato da categoria (uma linha).
""".strip()

        self.prompt = PromptTemplate.from_template(template)

        self.chat = ChatGroq(
            model=self.config.model,
            temperature=self.config.temperature,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )

        self.chain = self.prompt | self.chat | StrOutputParser()

    def extrair_parcela(self, lancamento: str):
        if pd.isna(lancamento):
            return pd.NA, pd.NA

        s = str(lancamento)
        matches = self.parc_re.findall(s)  # [('09','12'), ...]
        for a, t in reversed(matches):
            atual = int(a)
            total = int(t)
            if total >= 2 and 1 <= atual <= total:
                return atual, total

        return pd.NA, pd.NA

    def adicionar_parcelas(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df[["ParcelaAtual", "ParcelaTotal"]] = df["Lançamento"].apply(
            lambda x: pd.Series(self.extrair_parcela(x))
        )

        df["Parcela"] = df.apply(
            lambda r: f"{int(r['ParcelaAtual']):02d}/{int(r['ParcelaTotal']):02d}"
            if pd.notna(r["ParcelaTotal"]) else "",
            axis=1
        )

        df["Lancamento_Limpo"] = (
            df["Lançamento"]
            .str.replace(self.parc_re, " ", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        df = df[~df["Lancamento_Limpo"].astype(str).str.upper().str.contains("PAGAMENTO EFETUADO", na=False)]

        return df



    def categorizar_batch(self, df: pd.DataFrame, on_progress: Optional[Callable[[int, int], None]] = None) -> pd.DataFrame:
        df = df.copy()

        texts = df["Lancamento_Limpo"].astype(str).fillna("")
        texts_unicos = texts.unique().tolist()

        total = len(texts_unicos)
        categorias_unicas: List[str] = []
        bs = int(self.config.batch_size)

        # inicializa progresso
        if on_progress:
            on_progress(0, total)

        done = 0
        for i in range(0, total, bs):
            chunk = texts_unicos[i:i + bs]
            resps = self.chain.batch(chunk, config={"max_concurrency": self.config.max_concurrency})
            resps = [r.strip() for r in resps]
            categorias_unicas.extend(resps)

            done += len(chunk)
            if on_progress:
                on_progress(done, total)

            time.sleep(self.config.sleep_seconds)

        mapa_texto_para_cat: Dict[str, str] = dict(zip(texts_unicos, categorias_unicas))
        df["Categoria"] = texts.map(mapa_texto_para_cat)

        return df

    
    def _parse_valor(self, x) -> float:
      s = str(x).strip()
      s = s.replace("R$", "").replace(" ", "")

      # tenta lidar com 1.234,56 ou 1,234.56 ou 1234,56
      if re.search(r",\d{2}$", s):
          s = s.replace(".", "").replace(",", ".")
      elif re.search(r"\.\d{2}$", s):
          s = s.replace(",", "")
      else:
          s = s.replace(",", ".")

      return pd.to_numeric(s, errors="coerce")


    def ler_csv_cartao(self, file: FileLike) -> pd.DataFrame:
        """
        Lê CSV do cartão com colunas data/lançamento/valor.
        Aceita:
          - caminho (str)
          - UploadedFile do Streamlit (file-like)
          - file object
        """
        # Se for UploadedFile/file object, garante ponteiro no início
        if hasattr(file, "seek"):
            try:
                file.seek(0)
            except Exception:
                pass

        # tenta separadores/encodings comuns
        last_err = None
        for sep, enc in [(",", "utf-8"), (";", "utf-8"), (",", "latin-1"), (";", "latin-1")]:
            try:
                df = pd.read_csv(file, sep=sep, encoding=enc)
                last_err = None
                break
            except Exception as e:
                last_err = e
                # se for file-like, precisa voltar pro início antes de tentar de novo
                if hasattr(file, "seek"):
                    try:
                        file.seek(0)
                    except Exception:
                        pass
                continue

        if last_err is not None:
            raise last_err

        # normaliza nomes
        df.columns = [c.strip().lower() for c in df.columns]

        col_data = next((c for c in df.columns if "data" in c), None)
        col_lanc = next((c for c in df.columns if "lan" in c or "descr" in c), None)
        col_val = next((c for c in df.columns if "valor" in c or "amount" in c), None)

        if not all([col_data, col_lanc, col_val]):
            raise ValueError(f"Não achei as colunas. Encontrei: {df.columns.tolist()}")

        df = df[[col_data, col_lanc, col_val]].copy()
        df.columns = ["Data", "Lançamento", "Valor"]

        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
        df["Valor"] = df["Valor"].apply(self._parse_valor)

        df["Lançamento"] = (
            df["Lançamento"]
            .astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )

        df = df.dropna(subset=["Data", "Lançamento", "Valor"]).reset_index(drop=True)
        return df