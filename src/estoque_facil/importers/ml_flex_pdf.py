"""Parser da lista de etiquetas do Mercado Envios Flex (PDF) — ESCOPO.md §2.9.

Por que este módulo existe: **a planilha do ML (§2) não traz as vendas Flex.**
Quem só importa o Excel nunca dá baixa dessas vendas, e o estoque de casa vai
ficando alto demais. A lista de etiquetas que o ML gera na hora de despachar
traz todas elas — e traz o `N.º de venda`, que é a MESMA chave de idempotência
da planilha (§2.3). Ou seja: importar os dois arquivos não duplica baixa
nenhuma, mesmo que uma venda apareça nos dois.

O que o PDF **não** tem: valores, data da venda e status. Por isso a linha que
sai daqui vem com `tem_financeiro=False` e não escreve nada no balanço —
receita inventada é pior do que receita faltando (§5.8).

Três armadilhas que este parser existe para evitar:

  1. O PDF tem DUAS COLUNAS ("Identificação" e "Produtos"). O texto corrido as
     embaralha: o nome do comprador cai no meio dos dados do produto. A
     separação aqui é pela coordenada X de cada pedaço de texto, nunca pela
     ordem em que o PDF desenha.
  2. `SKU:` e o valor dele são pedaços SEPARADOS na mesma linha — só se juntam
     agrupando por Y (com tolerância: o título fica 0,1pt fora da linha).
  3. Uma etiqueta pode listar mais de um produto. Cada `SKU:` abre um item
     novo, e todos herdam o N.º de venda daquela etiqueta.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from .ml_vendas_xlsx import (
    ErroArquivoML,
    LinhaVenda,
    RelatorioML,
    classificar_local,
    data_do_nome,
)

# X que separa as colunas: "Identificação" começa em ~31, "Produtos" em ~261.
LIMITE_COLUNA = 200.0

# Duas células da mesma linha podem sair com Y levemente diferente — o título do
# produto vem 0,1pt acima do resto. Sem folga, cada uma viraria uma linha.
TOLERANCIA_LINHA = 3.0

RE_ID_ENVIO = re.compile(r"^\d{6,}$")
RE_VENDA = re.compile(r"^venda:\s*(\S+)", re.I)
RE_SKU = re.compile(r"^sku:\s*(.*)$", re.I)
RE_QUANTIDADE = re.compile(r"^quantidade:\s*(\d+)", re.I)
# Atributo é "Chave: valor" com chave curta ("Cor", "Nome do desenho"). Título de
# anúncio não tem dois-pontos — é isso que separa um do outro.
RE_ATRIBUTO = re.compile(r"^([^:]{1,30}):\s+(.+)$")

# Cabeçalho e rodapé repetidos em toda página. O "Identifiicação" com dois "i" é
# do próprio ML: comparar sem acento e aceitar as duas grafias.
CABECALHOS = ("identificacao", "identifiicacao", "produtos")
RODAPES = ("despachem as suas vendas", "nao demore")

ESTADO_FLEX = "Pronta para despachar (Flex)"
ENTREGA_FLEX = "Mercado Envios Flex"


class ErroArquivoFlex(ErroArquivoML):
    """PDF não é a lista de etiquetas. Herda de ErroArquivoML: a tela já trata."""


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _e_moldura(texto: str) -> bool:
    t = _sem_acento(texto).strip()
    return t in CABECALHOS or any(t.startswith(r) for r in RODAPES)


@dataclass
class _Pedaco:
    pagina: int
    y: float
    x: float
    texto: str


@dataclass
class _Etiqueta:
    """Uma etiqueta: a coluna da esquerda e a da direita, de cima para baixo."""

    envio: str = ""
    esquerda: list[str] = field(default_factory=list)
    direita: list[str] = field(default_factory=list)


def _ler_pedacos(caminho: Path) -> list[_Pedaco]:
    try:
        leitor = PdfReader(caminho)
        paginas = list(leitor.pages)
    except Exception as exc:  # noqa: BLE001
        raise ErroArquivoFlex(
            f"Não consegui abrir este PDF.\n\nDetalhe técnico: {exc}"
        ) from exc

    pedacos: list[_Pedaco] = []
    for n, pagina in enumerate(paginas):
        def visitar(texto, cm, tm, fonte, tamanho, _n=n):
            t = (texto or "").strip()
            if t and not _e_moldura(t):
                pedacos.append(_Pedaco(_n, float(tm[5]), float(tm[4]), t))

        try:
            pagina.extract_text(visitor_text=visitar)
        except Exception as exc:  # noqa: BLE001
            raise ErroArquivoFlex(
                f"Não consegui ler o texto da página {n + 1} deste PDF.\n\n"
                f"Detalhe técnico: {exc}"
            ) from exc
    return pedacos


def _linhas(pedacos: list[_Pedaco]) -> list[tuple[str, str]]:
    """Agrupa os pedaços em linhas visuais → (coluna esquerda, coluna direita)."""
    ordenados = sorted(pedacos, key=lambda p: (p.pagina, -p.y, p.x))
    linhas: list[tuple[str, str]] = []
    grupo: list[_Pedaco] = []

    def fechar():
        if not grupo:
            return
        esq = " ".join(p.texto for p in sorted(grupo, key=lambda p: p.x)
                       if p.x < LIMITE_COLUNA)
        dir_ = " ".join(p.texto for p in sorted(grupo, key=lambda p: p.x)
                        if p.x >= LIMITE_COLUNA)
        linhas.append((esq.strip(), dir_.strip()))
        grupo.clear()

    for p in ordenados:
        if grupo and (p.pagina != grupo[0].pagina or grupo[0].y - p.y > TOLERANCIA_LINHA):
            fechar()
        grupo.append(p)
    fechar()
    return linhas


def _etiquetas(linhas: list[tuple[str, str]]) -> list[_Etiqueta]:
    etiquetas: list[_Etiqueta] = []
    atual: _Etiqueta | None = None

    for esq, dir_ in linhas:
        if RE_ID_ENVIO.match(esq):
            atual = _Etiqueta(envio=esq)
            etiquetas.append(atual)
        elif atual is None and RE_VENDA.match(esq):
            # Etiqueta sem o número do envio no topo: a venda abre a etiqueta.
            atual = _Etiqueta()
            etiquetas.append(atual)
        if atual is None:
            continue
        if esq and not RE_ID_ENVIO.match(esq):
            atual.esquerda.append(esq)
        if dir_:
            atual.direita.append(dir_)
    return etiquetas


@dataclass
class _Item:
    sku: str
    titulo: str = ""
    quantidade: int | None = None
    atributos: list[str] = field(default_factory=list)


def _itens(etiqueta: _Etiqueta) -> list[_Item]:
    """Cada `SKU:` abre um item; o que vem antes é título, o que vem depois é atributo."""
    itens: list[_Item] = []
    titulo: list[str] = []

    for texto in etiqueta.direita:
        m = RE_SKU.match(texto)
        if m:
            itens.append(_Item(sku=m.group(1).strip(), titulo=" ".join(titulo).strip()))
            titulo = []
            continue
        m = RE_QUANTIDADE.match(texto)
        if m and itens:
            itens[-1].quantidade = int(m.group(1))
            continue
        m = RE_ATRIBUTO.match(texto)
        if m and itens:
            itens[-1].atributos.append(f"{m.group(1).strip()} : {m.group(2).strip()}")
            continue
        titulo.append(texto)
    return itens


def _data_do_pdf(caminho: Path) -> datetime | None:
    """A etiqueta é impressa no dia do despacho — a data do PDF serve de data da venda.

    Ordem: data no nome do arquivo, data de criação do PDF, data do arquivo em
    disco. O fuso é ignorado de propósito: vale a hora que o ML imprimiu.
    """
    do_nome = data_do_nome(caminho)
    if do_nome:
        return do_nome
    try:
        criacao = PdfReader(caminho).metadata.creation_date
        if criacao:
            return criacao.replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        pass
    try:
        return datetime.fromtimestamp(caminho.stat().st_mtime)
    except OSError:
        return None


def ler(caminho: str | Path) -> RelatorioML:
    caminho = Path(caminho)
    etiquetas = _etiquetas(_linhas(_ler_pedacos(caminho)))
    data = _data_do_pdf(caminho)

    linhas: list[LinhaVenda] = []
    avisos: list[str] = []
    sem_numero = sem_sku = 0

    for etiqueta in etiquetas:
        vendas = [m.group(1) for texto in etiqueta.esquerda
                  if (m := RE_VENDA.match(texto))]
        itens = _itens(etiqueta)
        if vendas and not itens:
            # Anúncio sem SKU: a etiqueta não imprime a linha "SKU:" e não há
            # com o que casar (o PDF também não traz o código MLB). Some da
            # importação, mas não em silêncio.
            sem_sku += 1
        for i, item in enumerate(itens):
            if not vendas:
                # Sem N.º de venda não há como impedir baixa repetida (§2.3):
                # a linha fica de fora e a tela avisa quantas foram.
                sem_numero += 1
                continue
            # Uma etiqueta com vários produtos e vários N.ºs de venda (pacote):
            # pareia na ordem em que os dois aparecem, que é como o ML imprime.
            numero = vendas[i] if i < len(vendas) else vendas[-1]
            aviso = ""
            quantidade = item.quantidade
            if quantidade is None:
                quantidade = 1
                aviso = "A etiqueta não trouxe a quantidade — considerei 1 unidade."
            linhas.append(
                LinhaVenda(
                    numero_venda=numero,
                    data=data,
                    sku=item.sku,
                    mlb="",
                    titulo=item.titulo,
                    variacao=" | ".join(item.atributos),
                    quantidade=quantidade,
                    local=classificar_local(ENTREGA_FLEX),
                    estado=ESTADO_FLEX,
                    forma_entrega=ENTREGA_FLEX,
                    deposito="",
                    devolvidas=0,
                    dev_destino="",
                    cancelada=False,
                    total=0.0,
                    preco_unitario=0.0,
                    linha_planilha=len(linhas) + 1,
                    tem_financeiro=False,
                    aviso=aviso,
                )
            )

    if sem_numero:
        avisos.append(
            f"{sem_numero} etiqueta(s) ficaram de fora: não achei o N.º de venda "
            "nelas, e sem ele eu não consigo garantir que a baixa não vai repetir."
        )
    if sem_sku:
        avisos.append(
            f"{sem_sku} etiqueta(s) ficaram de fora porque o anúncio não tem SKU. "
            "Cadastre o SKU no anúncio do Mercado Livre e a próxima etiqueta já vem "
            "certa; enquanto isso, dê baixa dessas por Ferramentas → Ajuste de estoque."
        )

    if not linhas:
        # Achou etiquetas mas não aproveitou nenhuma: o motivo já está no aviso,
        # e ele explica muito melhor do que "arquivo errado".
        raise ErroArquivoFlex(
            "\n\n".join(avisos) if avisos else
            "Este PDF não parece ser a lista de etiquetas do Mercado Livre.\n\n"
            "No Mercado Livre, vá em Vendas → Imprimir etiquetas e salve o PDF "
            "(o mesmo arquivo que você manda para a impressora)."
        )

    return RelatorioML(
        linhas=linhas,
        arquivo=caminho.name,
        periodo_inicio=data,
        periodo_fim=data,
        tipo="vendas_flex_pdf",
        avisos=avisos,
    )
