"""Lista de estoque — ESCOPO.md §5.2.4 e §6.

Kit nunca parece item simples: mostra "dá para montar" no lugar da quantidade e
tem o campo de estoque bloqueado.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import kits, repo
from ..core.models import TipoProduto
from .tela_produto import TelaProduto
from .widgets.comuns import celula, configurar_colunas, dica, titulo

COR_ALERTA = QColor("#b3261e")
COR_ATENCAO = QColor("#8a5300")
COR_KIT = QColor("#2f4f8f")


class TelaEstoque(QWidget):
    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(titulo("Estoque"))

        topo = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setObjectName("busca")
        self.busca.setPlaceholderText("Procurar por nome ou código…")
        self.busca.setClearButtonEnabled(True)

        # busca com pequeno atraso: 195 itens filtram instantâneo, mas evita
        # redesenhar a tabela a cada tecla
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.recarregar)
        self.busca.textChanged.connect(lambda _: self._timer.start())

        self.filtro = QComboBox()
        self.filtro.addItems(["Tudo", "Só itens", "Só kits", "Precisa comprar"])
        self.filtro.currentIndexChanged.connect(self.recarregar)

        bt_novo = QPushButton("Novo produto")
        bt_novo.setObjectName("primario")
        bt_novo.clicked.connect(self.novo_produto)

        topo.addWidget(self.busca, 1)
        topo.addWidget(self.filtro)
        topo.addWidget(bt_novo)
        lay.addLayout(topo)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(
            ["Código", "Produto", "Tipo", "Em estoque", "Observação"]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setDefaultSectionSize(38)
        # Produto estica; o resto tem largura fixa para nada ser espremido
        configurar_colunas(self.tabela, [250, None, "auto", "auto", 250])
        self.tabela.doubleClicked.connect(self.abrir_selecionado)
        lay.addWidget(self.tabela, 1)

        self.rodape = dica("")
        lay.addWidget(self.rodape)
        self.recarregar()

    # ------------------------------------------------------------------ dados

    def _produtos(self):
        texto = self.busca.text()
        modo = self.filtro.currentText()
        if modo == "Só itens":
            return repo.buscar(self.session, texto, tipo=TipoProduto.SIMPLES)
        if modo == "Só kits":
            return repo.buscar(self.session, texto, tipo=TipoProduto.KIT)
        if modo == "Precisa comprar":
            return [p for p, _, _ in repo.abaixo_do_minimo(self.session)]
        return repo.buscar(self.session, texto)

    def recarregar(self):
        produtos = self._produtos()
        self.tabela.setRowCount(0)
        alertas = 0

        for p in produtos:
            d = kits.disponivel(self.session, p)
            linha = self.tabela.rowCount()
            self.tabela.insertRow(linha)

            self.tabela.setItem(linha, 0, celula(p.sku))
            self.tabela.setItem(linha, 1, celula(p.rotulo))

            tipo_item = QTableWidgetItem("Kit" if p.eh_kit else "Item")
            if p.eh_kit:
                tipo_item.setForeground(QBrush(COR_KIT))
            self.tabela.setItem(linha, 2, tipo_item)

            texto = f"Dá para montar {d.quantidade}" if p.eh_kit else str(d.quantidade)
            item_qtd = QTableWidgetItem(texto)
            item_qtd.setTextAlignment(Qt.AlignCenter)

            obs = ""
            if p.eh_kit and not kits.componentes_de(self.session, p):
                obs = "Sem composição"
                item_qtd.setForeground(QBrush(COR_ALERTA))
                alertas += 1
            elif p.eh_kit and d.gargalo is not None and d.quantidade <= (p.estoque_minimo or 0):
                obs = f"Limitado por {d.gargalo.rotulo}"
                item_qtd.setForeground(QBrush(COR_ATENCAO))
            elif d.quantidade < 0:
                obs = "Estoque negativo — confira"
                item_qtd.setForeground(QBrush(COR_ALERTA))
                alertas += 1
            elif p.estoque_minimo and d.quantidade <= p.estoque_minimo:
                travados = kits.kits_afetados(self.session, p) if not p.eh_kit else []
                obs = "Precisa comprar"
                if travados:
                    obs += f" — trava {len(travados)} kit(s)"
                item_qtd.setForeground(QBrush(COR_ALERTA))
                alertas += 1

            self.tabela.setItem(linha, 3, item_qtd)
            self.tabela.setItem(linha, 4, celula(obs))
            self.tabela.item(linha, 0).setData(Qt.UserRole, p.id)

        contagem = repo.contar(self.session)
        self.rodape.setText(
            f"Mostrando {len(produtos)} de {contagem['total']} produtos "
            f"({contagem['simples']} itens, {contagem['kits']} kits)."
            + (
                f"  {alertas} precisam de atenção." if alertas > 1
                else "  1 precisa de atenção." if alertas
                else ""
            )
        )

    # ------------------------------------------------------------------ ações

    def produto_selecionado(self):
        linha = self.tabela.currentRow()
        if linha < 0:
            return None
        pid = self.tabela.item(linha, 0).data(Qt.UserRole)
        from ..core.models import Produto

        return self.session.get(Produto, pid)

    def abrir_selecionado(self):
        p = self.produto_selecionado()
        if p is None:
            return
        if TelaProduto(self.session, p, self).exec():
            self.recarregar()

    def novo_produto(self):
        if TelaProduto(self.session, None, self).exec():
            self.recarregar()
