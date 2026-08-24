"""Balanço da loja — ESCOPO.md §5.8.

A pergunta que esta tela responde é uma só: **sobrou dinheiro no mês?**
Por isso a resposta aparece primeiro, em uma frase, e a conta que leva até ela
vem logo abaixo na ordem de um DRE simples — de cima (o que o comprador pagou)
para baixo (o que sobrou).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..services import financeiro
from .dialogos import DialogoDespesa, DialogoDespesas, campo_data, data_de
from .widgets.comuns import (
    NEGATIVO,
    POSITIVO,
    avisar,
    celula,
    celula_numero,
    configurar_colunas,
    dica,
    faixa,
    informar,
    moeda,
    numero,
    regua,
    rotulo,
    secao,
    titulo,
)

PERSONALIZADO = "Escolher as datas…"
ALTURA_LINHA = 34


class TelaBalanco(QWidget):
    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session
        self.balanco: financeiro.Balanco | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        # As ações vão na linha do título, e não junto do seletor de período:
        # em Archivo 700 os três botões mais as duas datas não cabiam em 1080px
        # de janela, e "Lançar despesa" saía cortada no meio da palavra.
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(10)
        cabecalho.addWidget(titulo("Balanço"))
        cabecalho.addStretch(1)

        bt_despesa = QPushButton("Lançar despesa")
        bt_despesa.setObjectName("primario")
        bt_despesa.clicked.connect(self.lancar_despesa)
        bt_despesas = QPushButton("Ver despesas")
        bt_despesas.clicked.connect(self.ver_despesas)
        bt_exportar = QPushButton("Exportar planilha")
        bt_exportar.clicked.connect(self.exportar)
        for b in (bt_despesas, bt_exportar, bt_despesa):
            cabecalho.addWidget(b)
        lay.addLayout(cabecalho)
        lay.addWidget(regua())

        # ------------------------------------------------------------- período
        topo = QHBoxLayout()
        topo.setSpacing(10)
        self.periodo = QComboBox()
        self._opcoes = financeiro.periodos()
        for nome, _i, _f in self._opcoes:
            self.periodo.addItem(nome)
        self.periodo.addItem(PERSONALIZADO)
        self.periodo.currentIndexChanged.connect(self._trocou_periodo)

        self.f_inicio = campo_data()
        self.f_fim = campo_data()
        self.lb_ate = QLabel("até")
        for w in (self.f_inicio, self.lb_ate, self.f_fim):
            w.setVisible(False)
        self.f_inicio.dateChanged.connect(self.recarregar)
        self.f_fim.dateChanged.connect(self.recarregar)

        topo.addWidget(rotulo("Período"))
        topo.addWidget(self.periodo)
        topo.addWidget(self.f_inicio)
        topo.addWidget(self.lb_ate)
        topo.addWidget(self.f_fim)
        topo.addStretch(1)
        lay.addLayout(topo)

        # ------------------------------------------------------------ resposta
        self.faixa_resultado = faixa("", "ok")
        lay.addWidget(self.faixa_resultado)

        # ------------------------------------------------- a conta e os produtos
        meio = QHBoxLayout()
        meio.setSpacing(16)

        coluna_conta = QVBoxLayout()
        coluna_conta.addWidget(secao("Como chegou nesse número"))
        self.tabela = QTableWidget(0, 2)
        self.tabela.setHorizontalHeaderLabels(["", "Valor"])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setSelectionMode(QTableWidget.NoSelection)
        self.tabela.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        configurar_colunas(self.tabela, [None, 150])
        self.tabela.setFixedWidth(470)
        coluna_conta.addWidget(self.tabela, 1)
        self.lb_despesas = dica("")
        coluna_conta.addWidget(self.lb_despesas)
        meio.addLayout(coluna_conta)

        coluna_produtos = QVBoxLayout()
        coluna_produtos.addWidget(secao("Onde o lucro foi feito"))
        self.tabela_produtos = QTableWidget(0, 5)
        self.tabela_produtos.setHorizontalHeaderLabels(
            ["Produto", "Un.", "Recebido", "Lucro", "Margem"]
        )
        self.tabela_produtos.verticalHeader().setVisible(False)
        self.tabela_produtos.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_produtos.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        configurar_colunas(self.tabela_produtos, [None, "auto", 110, 110, "auto"])
        coluna_produtos.addWidget(self.tabela_produtos, 1)
        meio.addLayout(coluna_produtos, 1)
        lay.addLayout(meio, 1)

        self.rodape = dica("")
        lay.addWidget(self.rodape)
        self.recarregar()

    # ------------------------------------------------------------------ período

    def _trocou_periodo(self):
        personalizado = self.periodo.currentText() == PERSONALIZADO
        for w in (self.f_inicio, self.lb_ate, self.f_fim):
            w.setVisible(personalizado)
        if personalizado:
            # abre já preenchido com o período que estava sendo visto
            if self.balanco is not None:
                for campo, valor in ((self.f_inicio, self.balanco.inicio),
                                     (self.f_fim, self.balanco.fim)):
                    campo.blockSignals(True)
                    campo.setDate(QDate(valor.year, valor.month, valor.day))
                    campo.blockSignals(False)
        self.recarregar()

    def periodo_atual(self) -> tuple[str, datetime, datetime]:
        if self.periodo.currentText() == PERSONALIZADO:
            inicio = data_de(self.f_inicio)
            fim = financeiro.fim_do_dia(data_de(self.f_fim))
            return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}", inicio, fim
        return self._opcoes[self.periodo.currentIndex()]

    # -------------------------------------------------------------------- dados

    def recarregar(self):
        nome, inicio, fim = self.periodo_atual()
        if inicio > fim:
            self.faixa_resultado.atualizar(
                "A data inicial está depois da final — inverta as duas.", "alerta"
            )
            return
        self.balanco = financeiro.apurar(self.session, inicio, fim)
        self._desenhar_resultado(nome)
        self._desenhar_conta()
        self._desenhar_produtos()

    def _desenhar_resultado(self, nome: str):
        b = self.balanco
        if not b.tem_dados:
            self.faixa_resultado.atualizar(
                "Nenhuma venda, despesa ou perda neste período. "
                "Importe as vendas do Mercado Livre para o balanço aparecer.",
                "alerta",
            )
            return
        verbo = "Sobrou" if b.lucro >= 0 else "Faltou"
        texto = (
            f"{verbo} {moeda(abs(b.lucro))} em {nome.lower()} — "
            f"margem de {numero(b.margem)}% sobre {moeda(b.receita_produtos)} "
            f"vendidos em {b.vendas} venda(s)."
        )
        if b.linhas_sem_custo:
            texto += (
                f" Atenção: {b.linhas_sem_custo} linha(s) sem custo cadastrado — "
                "o lucro real é menor."
            )
        self.faixa_resultado.atualizar(texto, "ok" if b.lucro >= 0 else "alerta")

    def _desenhar_conta(self):
        b = self.balanco
        self.tabela.setRowCount(0)
        negrito = QFont()
        negrito.setBold(True)

        for texto, valor, tipo in b.linhas():
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            forte = tipo in ("subtotal", "resultado")
            item_rotulo = celula(texto)
            # a coluna de dinheiro é sempre tabular: é uma conta sendo lida de
            # cima para baixo, e vírgula fora de prumo atrapalha a soma de olho
            item_valor = celula_numero(moeda(valor), negrito=forte)
            if forte:
                item_rotulo.setFont(negrito)
            if tipo == "resultado":
                # paleta mono: sobrou é tinta cheia, faltou é vermelho escuro
                cor = QColor(POSITIVO if valor >= 0 else NEGATIVO)
                item_rotulo.setForeground(QBrush(cor))
                item_valor.setForeground(QBrush(cor))
            elif round(valor, 2) < 0:
                item_valor.setForeground(QBrush(QColor(NEGATIVO)))
            self.tabela.setItem(i, 0, item_rotulo)
            self.tabela.setItem(i, 1, item_valor)

        altura = (self.tabela.horizontalHeader().height() or 30)
        self.tabela.setFixedHeight(altura + ALTURA_LINHA * self.tabela.rowCount() + 4)

        if b.despesas_por_categoria:
            partes = ", ".join(
                f"{nome} {moeda(valor)}"
                for nome, valor in sorted(
                    b.despesas_por_categoria.items(), key=lambda kv: -kv[1]
                )
            )
            self.lb_despesas.setText(f"Despesas do período: {partes}.")
        else:
            self.lb_despesas.setText(
                "Nenhuma despesa lançada no período — use “Lançar despesa”."
            )

    def _desenhar_produtos(self):
        linhas = financeiro.por_produto(
            self.session, self.balanco.inicio, self.balanco.fim, limite=30
        )
        self.tabela_produtos.setRowCount(0)
        for linha in linhas:
            i = self.tabela_produtos.rowCount()
            self.tabela_produtos.insertRow(i)
            self.tabela_produtos.setItem(i, 0, celula(linha.titulo))
            self.tabela_produtos.setItem(i, 1, celula_numero(str(linha.unidades)))
            for coluna, valor in ((2, linha.receita), (3, linha.lucro)):
                item = celula_numero(moeda(valor))
                if round(valor, 2) < 0:
                    item.setForeground(QBrush(QColor(NEGATIVO)))
                self.tabela_produtos.setItem(i, coluna, item)
            margem = celula_numero(f"{linha.margem:.0f}%" if linha.receita else "—")
            if linha.custo <= 0:
                margem.setText("sem custo")
                margem.setToolTip(
                    "Este produto não tem custo cadastrado, então a margem está inflada."
                )
            self.tabela_produtos.setItem(i, 4, margem)

        b = self.balanco
        self.rodape.setText(
            f"Período de {b.periodo_rotulo} · {b.unidades} unidades vendidas"
            + (f", {b.devolvidas} devolvidas" if b.devolvidas else "")
            + f" · ticket médio de {moeda(b.ticket_medio)}."
        )

    # -------------------------------------------------------------------- ações

    def lancar_despesa(self):
        if DialogoDespesa(self.session, self).exec():
            self.recarregar()

    def ver_despesas(self):
        _rotulo, inicio, fim = self.periodo_atual()
        DialogoDespesas(self.session, inicio, fim, self).exec()
        self.recarregar()

    def exportar(self):
        if self.balanco is None:
            return
        sugerido = f"balanco-{self.balanco.inicio:%Y-%m-%d}.csv"
        destino, _ = QFileDialog.getSaveFileName(
            self, "Onde salvar a planilha", sugerido, "Planilha (*.csv)"
        )
        if not destino:
            return
        try:
            caminho = financeiro.exportar_csv(self.session, self.balanco, Path(destino))
        except Exception as exc:  # noqa: BLE001
            avisar(self, "Não consegui salvar a planilha", str(exc),
                   detalhe_tecnico=repr(exc))
            return
        informar(self, "Planilha pronta",
                 f"Salvo em:\n{caminho}\n\nEle abre direto no Excel.")
