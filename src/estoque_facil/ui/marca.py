"""Marca Estoque Fácil — manual da marca, seções 01 a 05.

Fonte única dos tokens visuais. Nenhum hex de cor e nenhum tamanho de fonte
deve ser escrito à mão em outro arquivo: tudo sai daqui ou do `style.qss`,
que é gerado a partir daqui.

Sobre a escala tipográfica: o manual dá os tamanhos em px, mas o ESCOPO.md §6
fixa o corpo do texto em 14pt porque a usuária não enxerga bem de perto. Os
dois batem — 14px do manual vira 14pt aqui, e o resto da escala acompanha na
mesma proporção. Ler os px do manual como pt é o que mantém a hierarquia do
manual sem encolher a letra.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPixmap,
)

RECURSOS = Path(__file__).resolve().parent.parent / "resources"

# --------------------------------------------------------------------- cor
# Manual §03. Paleta mono: tinta sobre fundo claro, com um único vermelho.

VERMELHO = "#EC3013"          # símbolo, ação primária, pequenas ênfases
VERMELHO_ESCURO = "#B32309"   # texto pequeno em vermelho, estado pressionado
TINTA = "#201E1D"             # texto, réguas
FUNDO = "#F3F2F2"             # fundo da aplicação
SUPERFICIE = "#FFFFFF"        # cartões, tabelas, painéis
CINZA = "#6F6863"             # rótulos, texto secundário

# Derivadas — só claridades da tinta, nenhuma cor nova.
LINHA = "#D8D5D3"             # hairline de cartão e tabela
LINHA_CLARA = "#ECEAE9"       # grade interna das tabelas
SELECAO = "#DCD9D7"           # linha selecionada (texto continua legível em cima)
DESABILITADO = "#A29B96"

# Papéis semânticos. A paleta é mono: "positivo" é tinta, não verde.
POSITIVO = TINTA
NEGATIVO = VERMELHO_ESCURO
SECUNDARIO = CINZA

# ---------------------------------------------------------------- tipografia
# Manual §04. Uma família só, em títulos e em texto.

FAMILIA_PADRAO = "Archivo"
# Grotescas de sistema, na ordem em que o Qt deve tentar se o Archivo faltar.
FALLBACK = "Helvetica Neue, Segoe UI, Roboto, Arial, sans-serif"

CORPO = 14        # texto
ROTULO = 12       # caixa alta, entreletra 0,18em
SUBTITULO = 18
TITULO = 26
DISPLAY = 40
NUMERO = 34       # tabular

_familia_carregada: str | None = None


def carregar_fontes() -> str:
    """Registra os pesos do Archivo empacotados e devolve a família a usar.

    São três arquivos estáticos — 400, 600 e 700, os pesos do manual §04 — e
    não a fonte variável do Google Fonts. A variável funcionava no macOS e
    falhava no Linux: o eixo `wght` dela tem 600 como padrão, o nameID 1 é
    "Archivo SemiBold", e o Qt sobre fontconfig lê justamente esse nome. O
    resultado era 400, 500 e 600 saindo idênticos (todos no padrão) e o 700
    virando negrito sintético em vez do Bold desenhado.

    `packaging/fontes/gerar_estaticas.py` refaz os três a partir da variável.

    O caminho precisa ser absoluto: o CoreText recusa o relativo dependendo de
    onde o processo foi aberto. `RECURSOS` já vem de `__file__.resolve()`.

    Se nada registrar, o app não quebra — cai na pilha de grotescas do sistema.
    """
    global _familia_carregada
    if _familia_carregada is not None:
        return _familia_carregada

    familias: list[str] = []
    for arquivo in sorted((RECURSOS / "fontes").glob("*.ttf")):
        ident = QFontDatabase.addApplicationFont(str(arquivo))
        if ident != -1:
            familias += QFontDatabase.applicationFontFamilies(ident)

    # O SemiBold registra duas famílias: "Archivo" (a tipográfica, nameID 16) e
    # "Archivo SemiBold" (a legada, nameID 1 — a convenção OpenType só deixa
    # Regular/Bold/Italic morarem na mesma família legada). Quem interessa é a
    # tipográfica, que é a que casa com os três pesos.
    _familia_carregada = (
        FAMILIA_PADRAO if FAMILIA_PADRAO in familias
        else (familias[0] if familias else FAMILIA_PADRAO)
    )
    return _familia_carregada


def familia() -> str:
    return carregar_fontes()


def pilha_de_fontes() -> str:
    """A família seguida do fallback, no formato que o QSS entende."""
    return f'"{familia()}", {FALLBACK}'


def fonte(tamanho: int = CORPO, peso: int = 400, caixa_alta: bool = False,
          entreletra: float = 0.0) -> QFont:
    """QFont da marca — para onde o QSS não alcança (itens de tabela, pintura)."""
    f = QFont(familia(), tamanho)
    f.setWeight(QFont.Weight(peso))
    if caixa_alta:
        f.setCapitalization(QFont.AllUppercase)
    if entreletra:
        # em em: o Qt trabalha em porcentagem da largura do glifo
        f.setLetterSpacing(QFont.PercentageSpacing, 100 + entreletra * 100)
    return f


def fonte_tabular(tamanho: int = CORPO, peso: int = 400) -> QFont:
    """Manual §04: números sempre tabulares nas tabelas de estoque.

    No Archivo o "1" proporcional é ~30% mais estreito que os outros dígitos,
    então uma coluna de dinheiro sem `tnum` sai com as vírgulas fora de prumo.
    O recurso é do Qt 6.7 em diante; em versão mais velha a fonte volta a ser
    a normal, que continua legível — só não alinha.
    """
    f = fonte(tamanho, peso)
    try:
        f.setFeature(QFont.Tag("tnum"), 1)
    except Exception:  # noqa: BLE001
        pass
    return f


# --------------------------------------------------------------- o símbolo
# Manual §01. Grade de 100 × 100, larguras 10/16/8/20 nas posições 14/30/52/66.
# A variante de três barras é obrigatória abaixo de 24 px.

BARRAS = ((14, 10), (30, 16), (52, 8), (66, 20))
BARRAS_3 = ((18, 12), (40, 16), (66, 18))
BARRA_TOPO, BARRA_BASE = 20, 80
LIMITE_3_BARRAS = 24


def desenhar_simbolo(pintor: QPainter, retangulo: QRectF,
                     campo: str = VERMELHO, barras: str = SUPERFICIE) -> None:
    """Pinta o símbolo dentro do retângulo, na geometria exata do manual.

    Desenhado e não carregado do SVG de propósito: em 22 px na barra de título
    o rasterizador do SVG arredonda as barras para larguras iguais, e o ritmo
    desigual é justamente o que faz o símbolo ler como código de barras (§01).
    """
    lado = min(retangulo.width(), retangulo.height())
    x0, y0, u = retangulo.x(), retangulo.y(), lado / 100.0
    grupo = BARRAS_3 if lado < LIMITE_3_BARRAS else BARRAS

    pintor.save()
    pintor.setRenderHint(QPainter.Antialiasing, False)   # §05: sem suavizar a régua
    pintor.setPen(Qt.NoPen)
    pintor.fillRect(QRectF(x0, y0, lado, lado), QColor(campo))
    cor = QColor(barras)
    for x, largura in grupo:
        pintor.fillRect(
            QRectF(x0 + x * u, y0 + BARRA_TOPO * u,
                   largura * u, (BARRA_BASE - BARRA_TOPO) * u),
            cor,
        )
    pintor.restore()


@lru_cache(maxsize=32)
def simbolo(px: int, campo: str = VERMELHO, barras: str = SUPERFICIE) -> QPixmap:
    """Símbolo como pixmap quadrado de `px` de lado."""
    mapa = QPixmap(px, px)
    mapa.fill(Qt.transparent)
    pintor = QPainter(mapa)
    desenhar_simbolo(pintor, QRectF(0, 0, px, px), campo, barras)
    pintor.end()
    return mapa


@lru_cache(maxsize=4)
def icone_do_app() -> QIcon:
    """Ícone da janela e da barra de tarefas.

    Manual §05: quadrado cheio, sem borda e sem sombra — o sistema aplica a
    máscara que quiser. Usa os PNGs de geometria exata, que existem justamente
    para os tamanhos pequenos.
    """
    icone = QIcon()
    pasta = RECURSOS / "marca"
    for tamanho in (16, 32, 48, 64, 128, 256, 512, 1024):
        arquivo = pasta / f"icone-{tamanho}.png"
        if arquivo.exists():
            icone.addFile(str(arquivo))
    if icone.isNull():
        for tamanho in (16, 32, 64, 128, 256):
            icone.addPixmap(simbolo(tamanho))
    return icone


def caminho(nome: str) -> Path:
    """Caminho de um arquivo da pasta de marca (SVG ou PNG)."""
    return RECURSOS / "marca" / nome


def _url(arquivo: Path) -> str:
    """Caminho absoluto no formato que o `url()` do QSS aceita.

    Barra normal mesmo no Windows: o parser de folha de estilo do Qt trata a
    contrabarra como escape e engole o caminho.
    """
    return arquivo.as_posix()


# ------------------------------------------------------------ folha de estilo


def folha_de_estilo() -> str:
    """Lê o style.qss e substitui os tokens.

    O QSS fica em arquivo separado para poder ser lido e editado como CSS; as
    cores e a família da fonte entram aqui para não existirem em dois lugares.
    """
    arquivo = Path(__file__).resolve().parent / "style.qss"
    if not arquivo.exists():
        return ""
    css = arquivo.read_text(encoding="utf-8")
    tokens = {
        "FONTE": pilha_de_fontes(),
        # Setas e marca de seleção como arquivo: o truque de montar triângulo
        # com `border` no QSS não funciona no Qt — sai um retângulo preto.
        "SETA_BAIXO": _url(caminho("seta-baixo.svg")),
        "SETA_CIMA": _url(caminho("seta-cima.svg")),
        "SELECIONADO": _url(caminho("marca-selecionado.svg")),
        "VERMELHO": VERMELHO,
        "VERMELHO_ESCURO": VERMELHO_ESCURO,
        "TINTA": TINTA,
        "FUNDO": FUNDO,
        "SUPERFICIE": SUPERFICIE,
        "CINZA": CINZA,
        "LINHA": LINHA,
        "LINHA_CLARA": LINHA_CLARA,
        "SELECAO": SELECAO,
        "DESABILITADO": DESABILITADO,
        "CORPO": f"{CORPO}pt",
        "ROTULO": f"{ROTULO}pt",
        "SUBTITULO": f"{SUBTITULO}pt",
        "TITULO": f"{TITULO}pt",
        "DISPLAY": f"{DISPLAY}pt",
        "NUMERO": f"{NUMERO}pt",
    }
    for chave, valor in tokens.items():
        css = css.replace(f"@{chave}@", valor)
    return css
