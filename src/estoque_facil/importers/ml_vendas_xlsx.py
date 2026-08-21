"""Parser do relatório de vendas do Mercado Livre — ESCOPO.md §2.

Especificação vinda da leitura de um arquivo real, não de documentação.
As três armadilhas que este módulo existe para evitar:

  1. As colunas 8, 49 e 62 têm TODAS o nome "Unidades" (blocos Vendas, Devoluções
     e Reclamações). As 43 e 50 são ambas "Forma de entrega". Por isso tudo aqui
     é lido por ÍNDICE, nunca por nome.
  2. Células "vazias" do ML vêm como ' ' (um espaço), não None.
  3. O relatório NÃO é do dia: um arquivo de 21/08 trouxe vendas de 12 a 21/08.
     Relatórios se sobrepõem — a deduplicação é por N.º de venda (§2.3).
"""
from __future__ import annotations

import re
import unicodedata
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import openpyxl

# O ML gera XLSX sem estilo padrão; o aviso do openpyxl só polui o log.
warnings.filterwarnings("ignore", message="Workbook contains no default style")

MESES = {
    m: i
    for i, m in enumerate(
        "janeiro fevereiro março abril maio junho julho agosto "
        "setembro outubro novembro dezembro".split(),
        1,
    )
}

# Índices 1-based — ver a tabela da §2.2 do escopo.
COL = {
    "venda": 1,
    "data": 2,
    "deposito": 3,
    "estado": 4,
    "pacote": 6,
    "kit_ml": 7,
    "unidades": 8,
    "cancelamento": 18,
    "total": 19,
    "sku": 23,
    "mlb": 24,
    "titulo": 25,
    "variacao": 26,
    "preco": 27,
    "forma_entrega": 43,
    "transportador": 46,
    "dev_unidades": 49,
    "dev_resultado": 59,
    "dev_destino": 60,
}

MARCADOR_CABECALHO = "n.º de venda"
LINHAS_PARA_PROCURAR_CABECALHO = 15

# Status que NÃO abatem estoque. Configurável (§2.7): status desconhecido abate,
# mas marca a linha para revisão — nunca falha em silêncio.
STATUS_NAO_ABATE = ("cancelad", "não concretizad", "nao concretizad")

# Classificação casa × Full pela forma de entrega, NUNCA pelo nome do depósito,
# que é texto livre definido pelo vendedor (§2.5).
MARCAS_FULL = ("fulfillment", "full")


class ErroArquivoML(Exception):
    """Arquivo não é o relatório esperado. Mensagem já pronta para a tela."""


def _limpa(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def parse_data(txt: str) -> datetime | None:
    """'21 de agosto de 2026 16:10 hs.' — sem depender de locale, que varia por SO."""
    m = re.match(r"(\d{1,2}) de (\S+) de (\d{4})(?:\s+(\d{1,2}):(\d{2}))?", _limpa(txt), re.I)
    if not m:
        return None
    dia, mes, ano, hora, minuto = m.groups()
    mes = unicodedata.normalize("NFC", mes.lower())
    if mes not in MESES:
        return None
    return datetime(int(ano), MESES[mes], int(dia), int(hora or 0), int(minuto or 0))


def _data_do_nome(caminho: Path) -> datetime | None:
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", caminho.name)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _inteiro(txt: str) -> int:
    if not txt:
        return 0
    try:
        v = float(txt.replace(",", "."))
    except ValueError:
        return 0
    if abs(v - round(v)) > 0.001:
        return 0
    return int(round(v))


def classificar_local(forma_entrega: str) -> str:
    from ..core.models import CASA, FULL

    f = _sem_acento(forma_entrega)
    return FULL if any(m in f for m in MARCAS_FULL) else CASA


@dataclass
class LinhaVenda:
    numero_venda: str
    data: datetime | None
    sku: str
    mlb: str
    titulo: str
    variacao: str
    quantidade: int
    local: str
    estado: str
    forma_entrega: str
    deposito: str
    devolvidas: int
    dev_destino: str
    cancelada: bool
    total: float
    preco_unitario: float
    linha_planilha: int

    @property
    def abate(self) -> bool:
        if self.cancelada or self.quantidade <= 0:
            return False
        estado = _sem_acento(self.estado)
        return not any(marca in estado for marca in STATUS_NAO_ABATE)

    @property
    def status_desconhecido(self) -> bool:
        """Status que nunca vimos: abate, mas a linha vai marcada para revisão (§2.7)."""
        conhecidos = ("pronta para", "para enviar", "enviad", "entregue", "a caminho",
                      "cancelad", "nao concretizad", "pronto para")
        e = _sem_acento(self.estado)
        return not any(c in e for c in conhecidos)


@dataclass
class RelatorioML:
    linhas: list[LinhaVenda]
    arquivo: str
    periodo_inicio: datetime | None
    periodo_fim: datetime | None

    @property
    def total_unidades(self) -> int:
        return sum(ln.quantidade for ln in self.linhas if ln.abate)


def _achar_cabecalho(rows) -> int:
    """Não fixar 'linha 6': procurar a célula 'N.º de venda' (§2.1)."""
    for i, row in enumerate(rows[:LINHAS_PARA_PROCURAR_CABECALHO]):
        for cel in row:
            if _sem_acento(_limpa(cel)) == _sem_acento(MARCADOR_CABECALHO):
                return i
    raise ErroArquivoML(
        "Este arquivo não parece ser o relatório de vendas do Mercado Livre.\n\n"
        "No Mercado Livre, vá em Vendas → Exportar → Excel e escolha o período."
    )


def ler(caminho: str | Path) -> RelatorioML:
    caminho = Path(caminho)
    try:
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ErroArquivoML(
            f"Não consegui abrir o arquivo.\n\nDetalhe técnico: {exc}"
        ) from exc

    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ErroArquivoML("O arquivo está vazio.")

    inicio = _achar_cabecalho(rows)
    largura = len(rows[inicio])
    if largura < COL["sku"]:
        raise ErroArquivoML(
            "O relatório está com menos colunas do que o esperado — "
            "talvez seja o relatório de tarifas, e não o de vendas."
        )

    fallback = _data_do_nome(caminho)
    linhas: list[LinhaVenda] = []

    for offset, row in enumerate(rows[inicio + 1 :], start=inicio + 2):
        if not _limpa(row[0]):
            continue

        def g(chave: str, _row=row) -> str:
            idx = COL[chave] - 1
            return _limpa(_row[idx]) if idx < len(_row) else ""

        forma = g("forma_entrega")
        linhas.append(
            LinhaVenda(
                numero_venda=g("venda"),
                data=parse_data(g("data")) or fallback,
                sku=g("sku"),
                mlb=g("mlb"),
                titulo=g("titulo"),
                variacao=g("variacao"),
                quantidade=_inteiro(g("unidades")),
                local=classificar_local(forma),
                estado=g("estado"),
                forma_entrega=forma,
                deposito=g("deposito"),
                devolvidas=_inteiro(g("dev_unidades")),
                dev_destino=g("dev_destino"),
                cancelada=bool(g("cancelamento")),
                total=float(g("total").replace(",", ".") or 0),
                preco_unitario=float(g("preco").replace(",", ".") or 0),
                linha_planilha=offset,
            )
        )

    if not linhas:
        raise ErroArquivoML("O relatório não tem nenhuma venda no período escolhido.")

    datas = [ln.data for ln in linhas if ln.data]
    return RelatorioML(
        linhas=linhas,
        arquivo=caminho.name,
        periodo_inicio=min(datas) if datas else None,
        periodo_fim=max(datas) if datas else None,
    )
