"""Peças de interface reaproveitadas — ESCOPO.md §6 e manual da marca §04/§05."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import marca

# Papéis semânticos da paleta mono (manual §03). Não existe verde nem amarelo:
# "positivo" é a própria tinta, e o que pede ação é o vermelho escuro.
POSITIVO = marca.POSITIVO
SECUNDARIO = marca.SECUNDARIO
NEGATIVO = marca.NEGATIVO


LIMITE_TITULO = 36


def moeda(valor: float) -> str:
    """R$ 1.234,56 — ponto no milhar, vírgula no centavo, sinal antes do símbolo.

    Existe porque `f"R$ {v:.2f}"` escreve 1234.56, que ela lê como mil duzentos
    e trinta e quatro reais e cinquenta e seis... ou não lê.
    """
    sinal = "-" if round(valor, 2) < 0 else ""
    inteiro = f"{abs(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"{sinal}R$ {inteiro}"


def numero(valor: float, casas: int = 1) -> str:
    """Número com vírgula decimal — usado nas margens."""
    return f"{valor:.{casas}f}".replace(".", ",")


# --------------------------------------------------------------- tipografia


def titulo(texto: str, limite: int = LIMITE_TITULO) -> QLabel:
    """Título encurtado, com o texto inteiro no tooltip.

    Um nome longo de anúncio ("Kit Mordedor Mãozinha E Pezinho Para Gengiva
    Bebê Rosa…") empurrava a largura mínima do diálogo e cortava as colunas
    da direita. O nome completo continua na barra da janela e no tooltip.
    """
    curto = texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"
    lb = QLabel(curto)
    lb.setObjectName("titulo")
    if curto != texto:
        # Só o título que precisou ser cortado abre mão da própria largura: é
        # ele que empurrava o diálogo. Um título curto e fixo ("Balanço") com
        # política Ignorada some dentro de uma linha que tenha addStretch —
        # o Qt lhe dá largura zero.
        lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        lb.setToolTip(texto)
    else:
        lb.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    return lb


def display(texto: str) -> QLabel:
    lb = QLabel(texto)
    lb.setObjectName("display")
    return lb


def subtitulo(texto: str) -> QLabel:
    lb = QLabel(texto)
    lb.setObjectName("subtitulo")
    lb.setWordWrap(True)
    return lb


def dica(texto: str) -> QLabel:
    lb = QLabel(texto)
    lb.setObjectName("dica")
    lb.setWordWrap(True)
    return lb


def secao(texto: str) -> QLabel:
    """Cabeçalho de seção: rótulo caixa alta, entreletra larga (manual §04)."""
    lb = QLabel(texto.upper())
    lb.setObjectName("secao")
    return lb


def rotulo(texto: str) -> QLabel:
    lb = QLabel(texto.upper())
    lb.setObjectName("rotulo")
    return lb


def numero_grande(texto: str, negativo: bool = False) -> QLabel:
    """O nível "Número" do manual: 34, peso 700, tabular."""
    lb = QLabel(texto)
    lb.setObjectName("numeroNegativo" if negativo else "numero")
    lb.setFont(marca.fonte_tabular(marca.NUMERO, 700))
    return lb


def regua(clara: bool = False) -> QFrame:
    """A régua de 2px do manual — o único separador do sistema."""
    f = QFrame()
    f.setObjectName("reguaClara" if clara else "regua")
    f.setFixedHeight(1 if clara else 2)
    f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return f


# -------------------------------------------------------------------- marca


class Lockup(QWidget):
    """Lockup horizontal: símbolo + nome — manual §02.

    Pintado em vez de carregado do SVG porque o SVG usa texto vivo em Archivo:
    se a fonte não registrar, o arquivo sai sem nome nenhum. Aqui o nome é
    desenhado com a fonte que o app realmente carregou, e o respiro de 30% da
    altura do símbolo (§01) é garantido pela margem.
    """

    clicado = Signal()

    def __init__(self, altura: int = 22, assinatura: bool = False,
                 pai: QWidget | None = None):
        super().__init__(pai)
        self._altura = altura
        self._assinatura = assinatura
        self.setFixedHeight(self._altura_total())
        self.setMinimumWidth(self._largura())
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # A assinatura entra abaixo do nome, então o bloco fica mais alto que o símbolo.
    def _altura_total(self) -> int:
        return self._altura + (int(self._altura * 0.55) if self._assinatura else 0)

    def _fonte_nome(self):
        # nome a ~64% da altura do símbolo: é a proporção do lockup do manual
        return marca.fonte(max(8, int(self._altura * 0.64)), 700, entreletra=-0.035)

    def _fonte_assinatura(self):
        return marca.fonte(max(7, int(self._altura * 0.26)), 400, entreletra=0.26)

    def _largura(self) -> int:
        respiro = int(self._altura * 0.30)
        largura = self._altura + respiro + QFontMetrics(self._fonte_nome()).horizontalAdvance(
            "ESTOQUE FÁCIL"
        )
        if self._assinatura:
            largura = max(
                largura,
                self._altura + respiro
                + QFontMetrics(self._fonte_assinatura()).horizontalAdvance(
                    "CONTROLE DE ESTOQUE"
                ),
            )
        return largura + 4

    def sizeHint(self):
        from PySide6.QtCore import QSize

        return QSize(self._largura(), self._altura_total())

    def mouseReleaseEvent(self, evento):
        """Clicar na marca leva para o início — é o que o cursor de mão promete."""
        if evento.button() == Qt.LeftButton and self.rect().contains(evento.position().toPoint()):
            self.clicado.emit()
        super().mouseReleaseEvent(evento)

    def paintEvent(self, _evento):
        p = QPainter(self)
        marca.desenhar_simbolo(p, QRectF(0, 0, self._altura, self._altura))

        respiro = int(self._altura * 0.30)
        x = self._altura + respiro
        p.setPen(QColor(marca.TINTA))
        p.setFont(self._fonte_nome())
        metrica = QFontMetrics(self._fonte_nome())
        base = int(self._altura * 0.5 + metrica.capHeight() / 2)
        p.drawText(x, base, "ESTOQUE FÁCIL")

        if self._assinatura:
            p.setPen(QColor(marca.CINZA))
            p.setFont(self._fonte_assinatura())
            p.drawText(x + 1, base + int(self._altura * 0.42), "CONTROLE DE ESTOQUE")
        p.end()


# ------------------------------------------------------------------- botões


class CartaoBotao(QPushButton):
    """Cartão da tela inicial: título e explicação com pesos diferentes.

    Um QPushButton só sabe pintar um texto, com uma fonte. Os dois níveis do
    manual (subtítulo 600 + rótulo cinza) precisam de dois QLabel, então eles
    entram como filhos transparentes ao mouse — o `clicked` do botão continua
    valendo em toda a área.
    """

    def __init__(self, texto: str, descricao: str = "", pai: QWidget | None = None):
        super().__init__("", pai)
        self.setObjectName("cartao")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(6)

        self.lb_titulo = QLabel(texto)
        self.lb_titulo.setObjectName("subtituloCartao")
        self.lb_titulo.setWordWrap(True)
        lay.addWidget(self.lb_titulo)

        self.lb_descricao = QLabel(descricao)
        self.lb_descricao.setObjectName("dica")
        self.lb_descricao.setWordWrap(True)
        lay.addWidget(self.lb_descricao)
        self.lb_descricao.setVisible(bool(descricao))
        lay.addStretch(1)

        for filho in (self.lb_titulo, self.lb_descricao):
            filho.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            filho.setAlignment(Qt.AlignLeft | Qt.AlignTop)

    def setText(self, texto: str) -> None:      # noqa: N802 (API do Qt)
        """Mantém `setText` funcionando: quem chama espera trocar o título."""
        self.lb_titulo.setText(texto)

    def text(self) -> str:                       # noqa: N802 (API do Qt)
        return self.lb_titulo.text()


def botao_cartao(texto: str, descricao: str = "") -> CartaoBotao:
    """Os botões grandes da tela inicial."""
    return CartaoBotao(texto, descricao)


def botao_nav(texto: str, ativo: bool = False) -> QPushButton:
    """Item de navegação da barra de título: rótulo caixa alta (manual §05)."""
    b = QPushButton(texto.upper())
    b.setObjectName("nav")
    b.setCursor(Qt.PointingHandCursor)
    b.setFlat(True)
    marcar_ativo(b, ativo)
    return b


def marcar_ativo(botao: QPushButton, ativo: bool) -> None:
    """Liga a régua vermelha embaixo do item de navegação atual."""
    botao.setProperty("ativo", "true" if ativo else "false")
    botao.style().unpolish(botao)
    botao.style().polish(botao)


# ------------------------------------------------------------------- faixas


class Faixa(QFrame):
    """Faixa de aviso que se ATUALIZA em vez de ser substituída.

    A primeira versão trocava o widget inteiro com `layout().replaceWidget()`.
    Além de frágil, o QFrame novo entrava com a política de tamanho padrão e
    esticava verticalmente, engolindo o espaço da tela.

    O tipo não muda a cor do texto: muda a régua de 2px da esquerda — vermelha
    quando precisa de ação, tinta quando é só informação (manual §03).
    """

    def __init__(self, texto: str = "", tipo: str = "alerta", pai: QWidget | None = None):
        super().__init__(pai)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self._label = QLabel(texto)
        self._label.setObjectName("textoFaixa")
        self._label.setWordWrap(True)
        lay.addWidget(self._label, 1)
        # nunca esticar: a faixa ocupa só a altura do próprio texto
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.atualizar(texto, tipo)

    def atualizar(self, texto: str, tipo: str = "alerta") -> None:
        self._label.setText(texto)
        self.setObjectName("faixaOk" if tipo == "ok" else "faixaAlerta")
        self.setVisible(bool(texto))
        # reaplicar o QSS depois de trocar o objectName
        self.style().unpolish(self)
        self.style().polish(self)


def faixa(texto: str, tipo: str = "alerta") -> Faixa:
    return Faixa(texto, tipo)


def cartao(*widgets: QWidget) -> QFrame:
    f = QFrame()
    f.setObjectName("cartaoInfo")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(8)
    for w in widgets:
        lay.addWidget(w)
    return f


# ----------------------------------------------------------------- diálogos


def _vestir(caixa: QMessageBox) -> None:
    """Mensagem do sistema com a marca: ícone do app no lugar do ícone padrão.

    Manual §05 — o símbolo é o ícone do aplicativo; o ponto de exclamação
    colorido do Qt traz uma cor que não existe na paleta.
    """
    caixa.setIconPixmap(marca.simbolo(48))
    caixa.setWindowIcon(marca.icone_do_app())


def confirmar(pai: QWidget, titulo_txt: str, mensagem: str,
              ok_txt: str = "Confirmar") -> bool:
    """Confirmação em português claro, sempre com número (§6)."""
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(titulo_txt)
    caixa.setText(mensagem)
    _vestir(caixa)
    sim = caixa.addButton(ok_txt, QMessageBox.AcceptRole)
    sim.setObjectName("primario")
    caixa.addButton("Cancelar", QMessageBox.RejectRole)
    caixa.setDefaultButton(sim)
    caixa.exec()
    return caixa.clickedButton() is sim


def avisar(pai: QWidget, titulo_txt: str, mensagem: str,
           detalhe_tecnico: str = "") -> None:
    """Erro nunca é técnico. O detalhe fica atrás de um botão, para diagnóstico (§6)."""
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(titulo_txt)
    caixa.setText(mensagem)
    _vestir(caixa)
    if detalhe_tecnico:
        caixa.setDetailedText(detalhe_tecnico)
    caixa.addButton("Entendi", QMessageBox.AcceptRole)
    caixa.exec()


def informar(pai: QWidget, titulo_txt: str, mensagem: str) -> None:
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(titulo_txt)
    caixa.setText(mensagem)
    _vestir(caixa)
    caixa.addButton("Fechar", QMessageBox.AcceptRole)
    caixa.exec()


def linha(*widgets, espaco_no_fim: bool = True) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    for item in widgets:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, QWidget):
            lay.addWidget(item)
    if espaco_no_fim:
        lay.addStretch(0)
    return w


# ----------------------------------------------------------------- tabelas


def configurar_colunas(tabela, larguras: list) -> None:
    """Define como cada coluna se dimensiona.

    - `int`    → largura fixa em pixels (para colunas de conteúdo longo, como SKU)
    - `None`   → estica com a janela
    - `"auto"` → do tamanho do conteúdo (para textos curtos e previsíveis)

    Substitui `resizeColumnsToContents()` na tabela inteira, que dimensionava
    tudo pelo conteúdo mais longo — um SKU como
    `kitbrinquedobanhodino+fraldaM+lençohuggies` comia metade da largura e
    espremia as colunas que realmente importam.
    """
    cabecalho = tabela.horizontalHeader()
    # Manual §04: tudo alinhado à esquerda. O `text-align` do QSS não chega no
    # QHeaderView — quem manda no alinhamento do cabeçalho é esta chamada.
    cabecalho.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for i, largura in enumerate(larguras):
        if largura is None:
            cabecalho.setSectionResizeMode(i, QHeaderView.Stretch)
        elif largura == "auto":
            cabecalho.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        else:
            cabecalho.setSectionResizeMode(i, QHeaderView.Interactive)
            tabela.setColumnWidth(i, largura)


def celula(texto: str, tooltip: str | None = None) -> QTableWidgetItem:
    """Célula de tabela que guarda o texto inteiro no tooltip.

    Coluna estreita corta o texto; o tooltip garante que nada fique inacessível.
    """
    item = QTableWidgetItem(texto)
    item.setToolTip(tooltip or texto)
    return item


def celula_numero(texto: str, alinhamento=Qt.AlignRight | Qt.AlignVCenter,
                  negrito: bool = False) -> QTableWidgetItem:
    """Célula numérica com algarismos tabulares — manual §04.

    Sem isto as colunas de quantidade e de dinheiro desalinham a cada linha,
    porque no Archivo o "1" proporcional é mais estreito que os outros dígitos.
    """
    item = QTableWidgetItem(texto)
    item.setTextAlignment(alinhamento)
    item.setFont(marca.fonte_tabular(marca.CORPO, 700 if negrito else 400))
    return item
