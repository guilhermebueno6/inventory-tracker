"""Diálogos curtos: entrada de mercadoria, desfazer importação e excluir produto."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from sqlalchemy import select

from ..core import exclusao, kits, ledger, repo
from ..core.models import LoteImportacao, Produto, StatusLote, TipoProduto
from .widgets.comuns import (
    avisar,
    celula,
    configurar_colunas,
    confirmar,
    dica,
    informar,
    titulo,
)


class DialogoEntrada(QDialog):
    """Entrada de mercadoria — §5.4. Mostra o efeito nos kits depois de lançar."""

    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session
        self.setWindowTitle("Entrada de mercadoria")
        self.setMinimumWidth(600)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(titulo("Entrada de mercadoria"))
        lay.addWidget(dica("Registre o que chegou. Kits não entram aqui — só os itens."))

        form = QFormLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        for p in repo.buscar(session, tipo=TipoProduto.SIMPLES):
            self.combo.addItem(f"{p.rotulo}  ({p.sku})", p.id)

        self.qtd = QSpinBox()
        self.qtd.setRange(1, 999999)
        self.qtd.setValue(1)
        self.custo = QDoubleSpinBox()
        self.custo.setRange(0, 999999)
        self.custo.setDecimals(2)
        self.custo.setPrefix("R$ ")

        self.fornecedor = QLineEdit()
        self.fornecedor.setPlaceholderText("de quem você comprou (opcional)")

        form.addRow("Produto", self.combo)
        form.addRow("Quantidade que chegou", self.qtd)
        form.addRow("Custo por unidade (opcional)", self.custo)
        form.addRow("Fornecedor", self.fornecedor)
        lay.addLayout(form)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        bt_cancelar = QPushButton("Cancelar")
        bt_cancelar.clicked.connect(self.reject)
        bt_ok = QPushButton("Registrar entrada")
        bt_ok.setObjectName("primario")
        bt_ok.clicked.connect(self._salvar)
        rodape.addWidget(bt_cancelar)
        rodape.addWidget(bt_ok)
        lay.addLayout(rodape)

    def _salvar(self):
        pid = self.combo.currentData()
        if pid is None:
            avisar(self, "Escolha o produto", "Preciso saber o que chegou.")
            return
        produto = self.session.get(Produto, pid)
        antes = {k.id: kits.disponivel(self.session, k).quantidade
                 for k in kits.kits_afetados(self.session, produto)}
        fornecedor = self.fornecedor.text().strip()
        try:
            if fornecedor:
                produto.fornecedor = fornecedor
            ledger.entrada_compra(
                self.session, produto, self.qtd.value(),
                self.custo.value() or None,
                observacao=(
                    f"Entrada — fornecedor: {fornecedor}" if fornecedor
                    else "Entrada registrada na tela de mercadoria"
                ),
            )
            self.session.commit()
        except ledger.ErroEstoque as exc:
            self.session.rollback()
            avisar(self, "Não consegui registrar", str(exc))
            return

        ganho = []
        for kit_id, valor in antes.items():
            kit = self.session.get(Produto, kit_id)
            agora = kits.disponivel(self.session, kit).quantidade
            if agora > valor:
                ganho.append(f"{kit.rotulo}: {valor} → {agora}")

        msg = f"Entrada de {self.qtd.value()} registrada em {produto.rotulo}."
        if ganho:
            msg += "\n\nIsso destravou:\n" + "\n".join(f"  • {g}" for g in ganho)
        informar(self, "Pronto", msg)
        self.accept()


class DialogoImportacoes(QDialog):
    """Histórico de importações, com o botão de desfazer — §5.1 passo 8."""

    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session
        self.setWindowTitle("Importações")
        self.setMinimumSize(820, 460)

        lay = QVBoxLayout(self)
        lay.addWidget(titulo("Importações feitas"))
        lay.addWidget(dica("Desfazer devolve o estoque ao que era antes daquela importação."))

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(
            ["Quando", "Arquivo", "Período", "Vendas", "Situação", ""]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setDefaultSectionSize(44)
        configurar_colunas(self.tabela, [170, None, "auto", "auto", "auto", 130])
        lay.addWidget(self.tabela, 1)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        rodape = QHBoxLayout()
        rodape.addStretch(1)
        rodape.addWidget(fechar)
        lay.addLayout(rodape)
        self.recarregar()

    def recarregar(self):
        lotes = self.session.scalars(
            select(LoteImportacao).order_by(LoteImportacao.criado_em.desc())
        ).all()
        self.tabela.setRowCount(0)
        for lote in lotes:
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            self.tabela.setItem(i, 0, celula(f"{lote.criado_em:%d/%m/%Y %H:%M}"))
            self.tabela.setItem(i, 1, celula(lote.arquivo_nome))
            periodo = "—"
            if lote.periodo_inicio and lote.periodo_fim:
                periodo = f"{lote.periodo_inicio:%d/%m} a {lote.periodo_fim:%d/%m}"
            self.tabela.setItem(i, 2, QTableWidgetItem(periodo))
            qtd = QTableWidgetItem(str(lote.linhas_novas))
            qtd.setTextAlignment(Qt.AlignCenter)
            self.tabela.setItem(i, 3, qtd)
            self.tabela.setItem(
                i, 4,
                QTableWidgetItem("Desfeita" if lote.status == StatusLote.DESFEITO else "Aplicada"),
            )
            if lote.status != StatusLote.DESFEITO:
                bt = QPushButton("Desfazer")
                bt.setObjectName("perigo")
                bt.clicked.connect(lambda _, lid=lote.id: self._desfazer(lid))
                self.tabela.setCellWidget(i, 5, bt)

    def _desfazer(self, lote_id: int):
        lote = self.session.get(LoteImportacao, lote_id)
        if not confirmar(
            self,
            "Desfazer importação",
            f"Vou desfazer a importação de {lote.arquivo_nome} "
            f"({lote.linhas_novas} vendas).\n\n"
            "O estoque volta ao que era antes dela. "
            "Depois disso você pode importar o arquivo de novo.",
            "Desfazer",
        ):
            return
        try:
            qtd = ledger.desfazer_lote(self.session, lote_id)
            self.session.commit()
        except ledger.ErroEstoque as exc:
            self.session.rollback()
            avisar(self, "Não consegui desfazer", str(exc))
            return
        informar(self, "Desfeito", f"{qtd} movimentos removidos. O estoque foi restaurado.")
        self.recarregar()


# --------------------------------------------------------------- excluir produto
#
# Fica aqui, e não em cada tela, porque as três (estoque, produto e kits
# pendentes) precisam do MESMO fluxo — e um item excluído por um caminho mais
# frouxo que o outro seria justamente o bug que o §5.2.5 evita.


def excluir_produto(pai, session, produto) -> bool:
    """Exclui ou arquiva um produto, perguntando UMA coisa só (§6).

    Quem decide entre apagar e arquivar é `core.exclusao` — a tela só mostra a
    frase e o botão certo. Devolve True quando o produto saiu do catálogo.
    """
    analise = exclusao.analisar(session, produto)
    rotulo = produto.rotulo

    if analise.bloqueado:
        avisar(pai, "Este item faz parte de kits", analise.motivo_bloqueio)
        return False

    # Já arquivado e com histórico: arquivar de novo não faria nada, e apagar
    # levaria junto o item de vendas antigas. Dizer isso é melhor que um
    # botão que parece funcionar e não muda nada.
    if not analise.pode_excluir and not produto.ativo:
        avisar(
            pai,
            "Este produto não pode ser apagado",
            f"{rotulo} já está arquivado, e tem {analise.movimentos} "
            f"{'registro' if analise.movimentos == 1 else 'registros'} no "
            "histórico de vendas e entradas.\n\n"
            "Apagar de vez deixaria essas vendas antigas sem o item que saiu. "
            "Arquivado ele já não atrapalha: não aparece em listas, buscas nem "
            "alertas.",
        )
        return False

    if analise.pode_excluir:
        if not confirmar(pai, f"Excluir {rotulo}", analise.resumo, "Excluir de vez"):
            return False
        acao, feito = exclusao.excluir, "excluído de vez"
    else:
        if not confirmar(pai, f"Arquivar {rotulo}", analise.resumo, "Arquivar"):
            return False
        acao, feito = exclusao.arquivar, "arquivado"

    try:
        acao(session, produto)
        session.commit()
    except exclusao.ErroExclusao as exc:
        session.rollback()
        avisar(pai, "Não consegui excluir", str(exc))
        return False
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        avisar(pai, "Não consegui excluir", "Algo deu errado ao gravar.",
               detalhe_tecnico=repr(exc))
        return False

    informar(pai, "Pronto", f"{rotulo} foi {feito}.")
    return True


def reativar_produto(pai, session, produto) -> bool:
    """Traz um produto arquivado de volta para as listas."""
    rotulo = produto.rotulo
    if not confirmar(
        pai,
        f"Trazer {rotulo} de volta",
        f"{rotulo} volta a aparecer nas listas e nas buscas, "
        "com o estoque e o histórico que já tinha.",
        "Trazer de volta",
    ):
        return False
    exclusao.reativar(session, produto)
    session.commit()
    informar(pai, "Pronto", f"{rotulo} está de volta no catálogo.")
    return True
