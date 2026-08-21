"""Peças de interface reaproveitadas — ESCOPO.md §6."""
from __future__ import annotations

from PySide6.QtCore import Qt
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

VERDE = "#1b5e20"
AMARELO = "#8a5300"
VERMELHO = "#b3261e"


LIMITE_TITULO = 36


def titulo(texto: str, limite: int = LIMITE_TITULO) -> QLabel:
    """Título encurtado, com o texto inteiro no tooltip.

    Um nome longo de anúncio ("Kit Mordedor Mãozinha E Pezinho Para Gengiva
    Bebê Rosa…") empurrava a largura mínima do diálogo e cortava as colunas
    da direita. O nome completo continua na barra da janela e no tooltip.
    """
    curto = texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"
    lb = QLabel(curto)
    lb.setObjectName("titulo")
    lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    if curto != texto:
        lb.setToolTip(texto)
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
    lb = QLabel(texto)
    lb.setObjectName("secao")
    return lb


def botao_cartao(texto: str, descricao: str = "") -> QPushButton:
    """Os quatro botões grandes da tela inicial."""
    b = QPushButton(f"{texto}\n{descricao}" if descricao else texto)
    b.setObjectName("cartao")
    b.setCursor(Qt.PointingHandCursor)
    return b


class Faixa(QFrame):
    """Faixa de aviso que se ATUALIZA em vez de ser substituída.

    A primeira versão trocava o widget inteiro com `layout().replaceWidget()`.
    Além de frágil, o QFrame novo entrava com a política de tamanho padrão e
    esticava verticalmente, engolindo o espaço da tela.
    """

    def __init__(self, texto: str = "", tipo: str = "alerta", pai: QWidget | None = None):
        super().__init__(pai)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self._label = QLabel(texto)
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
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    for w in widgets:
        lay.addWidget(w)
    return f


def confirmar(pai: QWidget, titulo_txt: str, mensagem: str,
              ok_txt: str = "Confirmar") -> bool:
    """Confirmação em português claro, sempre com número (§6)."""
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(titulo_txt)
    caixa.setText(mensagem)
    caixa.setIcon(QMessageBox.Question)
    sim = caixa.addButton(ok_txt, QMessageBox.AcceptRole)
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
    caixa.setIcon(QMessageBox.Warning)
    if detalhe_tecnico:
        caixa.setDetailedText(detalhe_tecnico)
    caixa.addButton("Entendi", QMessageBox.AcceptRole)
    caixa.exec()


def informar(pai: QWidget, titulo_txt: str, mensagem: str) -> None:
    caixa = QMessageBox(pai)
    caixa.setWindowTitle(titulo_txt)
    caixa.setText(mensagem)
    caixa.setIcon(QMessageBox.Information)
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
