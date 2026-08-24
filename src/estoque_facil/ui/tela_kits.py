"""Tela 'Kits sem composição' — ESCOPO.md §5.2.1.

São 75 kits para configurar. Um assistente por produto seria lento demais, então
esta tela é uma lista com contador que ela vai descendo sem voltar ao menu.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import kits, repo
from ..core.models import Produto, TipoProduto
from ..services import sugestao
from .dialogos import excluir_produto
from .tela_produto import TelaProduto
from .widgets.comuns import (
    celula,
    celula_numero,
    configurar_colunas,
    dica,
    faixa,
    moeda,
    regua,
    titulo,
)


class TelaKitsPendentes(QWidget):
    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session

        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(12)
        self.lay.addWidget(titulo("Kits sem composição"))
        self.lay.addWidget(regua())
        self.lay.addWidget(
            dica(
                "Cada kit precisa saber de que itens é montado. "
                "Abra um, escolha os itens (as sugestões já vêm prontas) e salve."
            )
        )

        self.faixa_contador = faixa("")
        self.lay.addWidget(self.faixa_contador)

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(
            ["Código", "Nome", "Custo do kit", "Sugestões que encontrei"]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.verticalHeader().setDefaultSectionSize(38)
        # a coluna de sugestões é a mais útil daqui: é ela que estica
        configurar_colunas(self.tabela, [300, 210, "auto", None])
        self.tabela.doubleClicked.connect(self.abrir)
        self.lay.addWidget(self.tabela, 1)

        acoes = QHBoxLayout()
        # Nem todo kit pendente vale montar: o catálogo do ML traz anúncios que
        # ela já não vende. Poder excluir aqui é o que faz a lista chegar a zero.
        bt_excluir = QPushButton("Excluir este kit")
        bt_excluir.setObjectName("perigo")
        bt_excluir.clicked.connect(self.excluir)
        acoes.addWidget(bt_excluir)
        acoes.addStretch(1)
        bt = QPushButton("Montar este kit")
        bt.setObjectName("primario")
        bt.clicked.connect(self.abrir)
        acoes.addWidget(bt)
        self.lay.addLayout(acoes)

        self.recarregar()

    def recarregar(self):
        pendentes = kits.kits_sem_composicao(self.session)
        total = repo.contar(self.session)["kits"]
        prontos = total - len(pendentes)

        self.faixa_contador.atualizar(
            "Todos os kits estão configurados." if not pendentes
            else f"Faltam {len(pendentes)} de {total} kits. Já configurados: {prontos}.",
            "ok" if not pendentes else "alerta",
        )

        self.tabela.setRowCount(0)
        for p in pendentes:
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            self.tabela.setItem(i, 0, celula(p.sku))
            self.tabela.setItem(i, 1, celula(p.nome or "—"))
            self.tabela.setItem(i, 2, celula_numero(moeda(p.custo)))
            candidatos = sugestao.sugerir_componentes(self.session, p, 3)
            texto = ", ".join(c.rotulo for _s, c in candidatos) or "—"
            self.tabela.setItem(i, 3, celula(texto))
            self.tabela.item(i, 0).setData(Qt.UserRole, p.id)

    def _selecionado(self) -> Produto | None:
        i = self.tabela.currentRow()
        if i < 0:
            return None
        return self.session.get(Produto, self.tabela.item(i, 0).data(Qt.UserRole))

    def excluir(self):
        produto = self._selecionado()
        if produto is None:
            return
        if excluir_produto(self, self.session, produto):
            self.recarregar()

    def abrir(self):
        produto = self._selecionado()
        if produto is None:
            return
        if produto.tipo != TipoProduto.KIT:
            produto.tipo = TipoProduto.KIT
            self.session.flush()
        TelaProduto(self.session, produto, self).exec()
        self.recarregar()
