"""Diálogos curtos: entrada de mercadoria, movimentação manual de estoque,
histórico de movimentações, despesas, desfazer importação e excluir produto."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from sqlalchemy import select

from ..core import exclusao, kits, ledger, repo
from ..core.models import (
    ROTULOS_DESPESA,
    CategoriaDespesa,
    LoteImportacao,
    Produto,
    StatusLote,
    TipoProduto,
)
from ..services import compras, financeiro
from .widgets.comuns import (
    CampoDinheiro,
    avisar,
    celula,
    celula_numero,
    configurar_colunas,
    confirmar,
    dica,
    informar,
    moeda,
    regua,
    titulo,
)


def campo_data(valor: datetime | None = None) -> QDateEdit:
    """Data com calendário. Padrão é hoje — quase sempre é o que ela quer."""
    campo = QDateEdit()
    campo.setCalendarPopup(True)
    campo.setDisplayFormat("dd/MM/yyyy")
    d = valor or datetime.now()
    campo.setDate(QDate(d.year, d.month, d.day))
    return campo


def data_de(campo: QDateEdit) -> datetime:
    d = campo.date()
    return datetime(d.year(), d.month(), d.day())


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
        lay.addWidget(regua())
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
        self.custo = CampoDinheiro()

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
        lay.addWidget(regua())
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
            "O estoque volta ao que era antes dela, e essas vendas saem do "
            "balanço. Depois disso você pode importar o arquivo de novo.",
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
  
# ---------------------------------------------------------- lista de compras
#
# Fica aqui pelo mesmo motivo de `excluir_produto`: a tela de estoque e o menu
# chamam o MESMO fluxo, e uma lista exportada por um caminho com regra
# diferente da do outro seria pior do que não ter o botão.


def exportar_lista_de_compras(pai, session) -> bool:
    """Salva a lista de compras em CSV. Devolve True quando o arquivo saiu."""
    linhas = compras.lista_de_compras(session)
    if not linhas:
        informar(
            pai, "Nada para comprar",
            "Nenhum item está no limite do mínimo — nem o dos itens, nem o que "
            "os kits reservam.\n\nSe você espera ver algo aqui, confira se os "
            "mínimos estão preenchidos na tela do produto.",
        )
        return False

    sugerido = f"lista-de-compras-{datetime.now():%Y-%m-%d}.csv"
    destino, _ = QFileDialog.getSaveFileName(
        pai, "Onde salvar a lista de compras", sugerido, "Planilha (*.csv)"
    )
    if not destino:
        return False
    try:
        caminho, quantos = compras.exportar_csv(session, Path(destino))
    except Exception as exc:  # noqa: BLE001
        avisar(pai, "Não consegui salvar a lista", str(exc), detalhe_tecnico=repr(exc))
        return False

    total = compras.total_estimado(linhas)
    informar(
        pai, "Lista pronta",
        f"{quantos} item(ns) para comprar, {moeda(total)} estimados.\n\n"
        f"Salvo em:\n{caminho}\n\nEle abre direto no Excel.",
    )
    return True


class DialogoMovimento(QDialog):
    """Movimentação manual de estoque: entra, sai ou vira contagem — §5.5.

    Duas coisas que esta tela resolve e que antes eram trabalho manual:

    1. **Kit também entra aqui.** Perder 2 kits era abrir cada componente e
       lembrar a proporção de cada um. Agora ela escolhe o kit, e o app lança um
       movimento por componente, todos com o MESMO motivo.
    2. **O motivo não é enfeite**: ele decide o tipo do movimento, e o tipo
       decide se aquilo custa dinheiro no balanço (perda custa, contagem não).
    """

    def __init__(self, session, produto=None, pai=None):
        super().__init__(pai)
        self.session = session
        self.setWindowTitle("Movimentar estoque")
        self.setMinimumWidth(620)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(titulo("Movimentar estoque"))
        lay.addWidget(regua())
        lay.addWidget(dica(
            "O que entrou ou saiu sem ser venda: quebrou, sumiu, virou brinde — "
            "ou o resultado de uma contagem na prateleira. Kit pode ser lançado "
            "inteiro: os itens dele saem na proporção certa."
        ))

        form = QFormLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        for p in repo.buscar(session):
            # o sufixo é o que distingue kit de item numa lista de texto puro,
            # onde o peso da letra (o recurso usado nas tabelas) não existe
            sufixo = "  ·  kit" if p.eh_kit else ""
            self.combo.addItem(f"{p.rotulo}  ({p.sku}){sufixo}", p.id)
        if produto is not None:
            indice = self.combo.findData(produto.id)
            if indice >= 0:
                self.combo.setCurrentIndex(indice)
        # nome de anúncio é longo: sem isto o campo abre mostrando o FIM do texto
        # ("…cartável Médio (m)"), e ela não reconhece o produto (mesmo motivo do
        # setCursorPosition(0) da tela do produto)
        self.combo.lineEdit().setCursorPosition(0)
        self.combo.currentIndexChanged.connect(self._trocou_produto)

        self.motivo = QComboBox()
        for codigo, (rotulo, _tipo, _modo) in ledger.MOTIVOS_AJUSTE.items():
            self.motivo.addItem(rotulo, codigo)
        self.motivo.currentIndexChanged.connect(self._atualizar_saldo)

        self.qtd = QSpinBox()
        self.qtd.setRange(0, 999999)
        self.qtd.setValue(1)
        self.qtd.valueChanged.connect(self._atualizar_saldo)

        self.descricao = QLineEdit()
        self.descricao.setPlaceholderText("o que aconteceu (opcional, mas ajuda depois)")

        form.addRow("Produto ou kit", self.combo)
        form.addRow("O que aconteceu", self.motivo)
        form.addRow("Quantidade", self.qtd)
        form.addRow("Detalhe", self.descricao)
        lay.addLayout(form)

        self.lb_efeito = QLabel("")
        self.lb_efeito.setWordWrap(True)
        lay.addWidget(self.lb_efeito)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        bt_cancelar = QPushButton("Cancelar")
        bt_cancelar.clicked.connect(self.reject)
        bt_ok = QPushButton("Registrar movimentação")
        bt_ok.setObjectName("primario")
        bt_ok.clicked.connect(self._salvar)
        rodape.addWidget(bt_cancelar)
        rodape.addWidget(bt_ok)
        lay.addLayout(rodape)

        self._trocou_produto()

    def _produto(self):
        pid = self.combo.currentData()
        return self.session.get(Produto, pid) if pid is not None else None

    # ------------------------------------------------------------------ motivos

    def _trocou_produto(self):
        """Contar a prateleira não vale para kit — kit não fica na prateleira."""
        produto = self._produto()
        eh_kit = produto is not None and produto.eh_kit
        modelo = self.motivo.model()
        for i in range(self.motivo.count()):
            _rotulo, _tipo, modo = ledger.MOTIVOS_AJUSTE[self.motivo.itemData(i)]
            vale = not (eh_kit and modo == "exato")
            modelo.item(i).setEnabled(vale)
            if not vale and self.motivo.currentIndex() == i:
                self.motivo.setCurrentIndex(0)
        self._atualizar_saldo()

    def _modo(self) -> str:
        return ledger.MOTIVOS_AJUSTE[self.motivo.currentData()][2]

    def _atualizar_saldo(self):
        produto = self._produto()
        if produto is None:
            self.lb_efeito.setText("")
            return
        modo = self._modo()
        if produto.eh_kit:
            self.lb_efeito.setText(self._efeito_do_kit(produto, modo))
            return

        saldo = ledger.saldo_de(self.session, produto)
        if modo == "exato":
            # sem bloquear o sinal, escrever o saldo aqui reentra em
            # `_atualizar_saldo` pelo `valueChanged` que a prévia do kit usa
            self.qtd.blockSignals(True)
            self.qtd.setValue(saldo)
            self.qtd.blockSignals(False)
            self.lb_efeito.setText(
                f"{produto.rotulo} está com {saldo} no sistema. "
                "Digite quanto tem de verdade na prateleira."
            )
        elif modo == "entrada":
            self.lb_efeito.setText(f"{produto.rotulo} tem {saldo} — as unidades entram.")
        else:
            custo = (produto.custo or 0.0) * self.qtd.value()
            self.lb_efeito.setText(
                f"{produto.rotulo} tem {saldo} — as unidades saem do estoque"
                + (f" e entram no balanço como perda de {moeda(custo)}." if custo else ".")
            )

    def _efeito_do_kit(self, kit, modo: str) -> str:
        """Mostra a conta ANTES de lançar: é o que ela não conseguia fazer de cabeça."""
        comps = kits.componentes_de(self.session, kit)
        if not comps:
            return (
                f"{kit.rotulo} ainda não tem composição. "
                "Defina de que ele é montado antes de movimentá-lo."
            )
        unidades = self.qtd.value()
        sinal = "+" if modo == "entrada" else "−"
        detalhe = ", ".join(
            f"{sinal}{c.quantidade * unidades} {c.componente.rotulo}" for c in comps[:4]
        )
        resto = f" e mais {len(comps) - 4}" if len(comps) > 4 else ""
        verbo = "entram" if modo == "entrada" else "saem"
        return (
            f"{kit.rotulo} é um kit: o estoque dele são os itens. "
            f"Vou lançar {len(comps)} movimento(s) com o mesmo motivo — "
            f"{detalhe}{resto} — e essas unidades {verbo} do estoque."
        )

    # -------------------------------------------------------------------- ação

    def _salvar(self):
        produto = self._produto()
        if produto is None:
            avisar(self, "Escolha o produto", "Preciso saber o que movimentar.")
            return
        try:
            resultado = ledger.movimento_manual(
                self.session, produto, self.motivo.currentData(), self.qtd.value(),
                descricao=self.descricao.text(),
            )
            self.session.commit()
        except ledger.ErroEstoque as exc:
            self.session.rollback()
            avisar(self, "Não consegui registrar", str(exc))
            return

        if resultado.nada_mudou:
            informar(self, "Nada mudou",
                     "O sistema já estava com essa quantidade — não precisei ajustar nada.")
            self.accept()
            return

        informar(self, "Movimentação registrada", self._resumo(resultado))
        self.accept()

    def _resumo(self, resultado) -> str:
        linhas = [
            f"  • {m.produto.rotulo}: {m.quantidade:+d} — ficou com {m.saldo_apos}"
            for m in resultado.movimentos
        ]
        if resultado.produto.eh_kit:
            cabeca = (
                f"{resultado.unidades} × {resultado.produto.rotulo} "
                f"({resultado.motivo}). Lancei nos itens do kit:"
            )
        else:
            cabeca = f"{resultado.produto.rotulo} ({resultado.motivo}):"

        travados = [
            k.rotulo for k in self._kits_travados(resultado)
        ]
        msg = cabeca + "\n" + "\n".join(linhas)
        if travados:
            msg += "\n\nIsso deixou sem poder montar:\n" + "\n".join(
                f"  • {t}" for t in travados[:5]
            )
        return msg

    def _kits_travados(self, resultado) -> list:
        """Kits que ficaram em zero por causa desta movimentação (§5.2.4)."""
        vistos, travados = set(), []
        for mov in resultado.movimentos:
            for k in kits.kits_afetados(self.session, mov.produto):
                if k.id in vistos:
                    continue
                vistos.add(k.id)
                if kits.disponivel(self.session, k).quantidade <= 0:
                    travados.append(k)
        return travados


class DialogoMovimentacoes(QDialog):
    """O livro-razão na tela — auditoria do estoque (§4.1).

    Todo movimento passa pelo ledger, mas até aqui só dava para vê-los abrindo
    produto por produto. Esta lista responde "o que aconteceu com o estoque",
    incluindo o motivo escrito à mão em cada ajuste.
    """

    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session
        self.setWindowTitle("Movimentações do estoque")
        self.setMinimumSize(940, 520)

        lay = QVBoxLayout(self)
        lay.addWidget(titulo("Movimentações do estoque"))
        lay.addWidget(regua())
        lay.addWidget(dica(
            "Tudo o que entrou e saiu, do mais novo para o mais antigo. "
            "A busca também procura no motivo do ajuste."
        ))

        topo = QHBoxLayout()
        topo.setSpacing(10)
        self.busca = QLineEdit()
        self.busca.setObjectName("busca")
        self.busca.setPlaceholderText("Procurar por produto, código ou motivo…")
        self.busca.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.recarregar)
        self.busca.textChanged.connect(lambda _: self._timer.start())

        self.so_manuais = QCheckBox("Só o que foi lançado à mão")
        self.so_manuais.stateChanged.connect(self.recarregar)

        topo.addWidget(self.busca, 1)
        topo.addWidget(self.so_manuais)
        lay.addLayout(topo)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(
            ["Quando", "Produto", "O que foi", "Quantidade", "Ficou com", "Motivo"]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setDefaultSectionSize(38)
        configurar_colunas(self.tabela, [140, 240, None, "auto", "auto", 260])
        lay.addWidget(self.tabela, 1)

        self.rodape = dica("")
        lay.addWidget(self.rodape)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        linha_fim = QHBoxLayout()
        linha_fim.addStretch(1)
        linha_fim.addWidget(fechar)
        lay.addLayout(linha_fim)
        self.recarregar()

    def recarregar(self):
        movs = ledger.movimentacoes(
            self.session,
            texto=self.busca.text(),
            apenas_manuais=self.so_manuais.isChecked(),
        )
        self.tabela.setRowCount(0)
        for mov in movs:
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            quando = mov.data_evento or mov.criado_em
            self.tabela.setItem(i, 0, celula(f"{quando:%d/%m/%Y %H:%M}"))
            self.tabela.setItem(i, 1, celula(mov.produto.rotulo, mov.produto.sku))
            self.tabela.setItem(i, 2, celula(ledger.descrever(mov)))
            self.tabela.setItem(i, 3, celula_numero(f"{mov.quantidade:+d}"))
            self.tabela.setItem(i, 4, celula_numero(str(mov.saldo_apos)))
            self.tabela.setItem(i, 5, celula(mov.observacao or ""))

        self.rodape.setText(
            f"{len(movs)} movimentação(ões) — as mais recentes primeiro."
            if movs else "Nenhuma movimentação encontrada."
        )


class DialogoDespesa(QDialog):
    """Lançar uma despesa — §5.8. Descrição é obrigatória de propósito."""

    def __init__(self, session, pai=None):
        super().__init__(pai)
        self.session = session
        self.setWindowTitle("Lançar despesa")
        self.setMinimumWidth(620)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(titulo("Lançar despesa"))
        lay.addWidget(regua())
        lay.addWidget(dica(
            "Gastos da loja que não são mercadoria. Compra de produto não entra "
            "aqui — ela vira custo sozinha quando o produto é vendido."
        ))

        form = QFormLayout()
        self.data = campo_data()
        self.descricao = QLineEdit()
        self.descricao.setPlaceholderText("ex.: caixas de papelão, anúncio patrocinado…")
        self.categoria = QComboBox()
        for codigo in CategoriaDespesa:
            self.categoria.addItem(ROTULOS_DESPESA[codigo], str(codigo))
        self.valor = CampoDinheiro(maximo=9999999)
        self.observacao = QLineEdit()
        self.observacao.setPlaceholderText("nota fiscal, fornecedor… (opcional)")

        form.addRow("Data", self.data)
        form.addRow("O que foi", self.descricao)
        form.addRow("Tipo de gasto", self.categoria)
        form.addRow("Valor", self.valor)
        form.addRow("Observação", self.observacao)
        lay.addLayout(form)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        bt_cancelar = QPushButton("Cancelar")
        bt_cancelar.clicked.connect(self.reject)
        bt_ok = QPushButton("Lançar despesa")
        bt_ok.setObjectName("primario")
        bt_ok.clicked.connect(self._salvar)
        rodape.addWidget(bt_cancelar)
        rodape.addWidget(bt_ok)
        lay.addLayout(rodape)

    def _salvar(self):
        try:
            financeiro.registrar_despesa(
                self.session,
                self.descricao.text(),
                self.valor.value(),
                data=data_de(self.data),
                categoria=self.categoria.currentData(),
                observacao=self.observacao.text(),
            )
            self.session.commit()
        except financeiro.ErroFinanceiro as exc:
            self.session.rollback()
            avisar(self, "Não consegui lançar", str(exc))
            return
        self.accept()


class DialogoDespesas(QDialog):
    """Lista de despesas do período, com lançar e apagar — §5.8."""

    def __init__(self, session, inicio=None, fim=None, pai=None):
        super().__init__(pai)
        self.session = session
        hoje = datetime.now()
        padrao_inicio, padrao_fim = financeiro.mes(hoje.year, hoje.month)
        self._inicio = inicio or padrao_inicio
        self._fim = fim or padrao_fim

        self.setWindowTitle("Despesas")
        self.setMinimumSize(860, 480)

        lay = QVBoxLayout(self)
        lay.addWidget(titulo("Despesas"))
        lay.addWidget(regua())

        topo = QHBoxLayout()
        self.f_inicio = campo_data(self._inicio)
        self.f_fim = campo_data(self._fim)
        self.f_inicio.dateChanged.connect(self.recarregar)
        self.f_fim.dateChanged.connect(self.recarregar)
        topo.addWidget(QLabel("De"))
        topo.addWidget(self.f_inicio)
        topo.addWidget(QLabel("até"))
        topo.addWidget(self.f_fim)
        topo.addStretch(1)
        bt_nova = QPushButton("Lançar despesa")
        bt_nova.setObjectName("primario")
        bt_nova.clicked.connect(self.nova)
        topo.addWidget(bt_nova)
        lay.addLayout(topo)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(
            ["Data", "O que foi", "Tipo", "Valor", ""]
        )
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setDefaultSectionSize(44)
        configurar_colunas(self.tabela, [130, None, 230, 130, 110])
        lay.addWidget(self.tabela, 1)

        self.rodape = dica("")
        lay.addWidget(self.rodape)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        linha_fim = QHBoxLayout()
        linha_fim.addStretch(1)
        linha_fim.addWidget(fechar)
        lay.addLayout(linha_fim)
        self.recarregar()

    def _periodo(self):
        return data_de(self.f_inicio), financeiro.fim_do_dia(data_de(self.f_fim))

    def nova(self):
        if DialogoDespesa(self.session, self).exec():
            self.recarregar()

    def recarregar(self):
        inicio, fim = self._periodo()
        despesas = financeiro.listar_despesas(self.session, inicio, fim)
        self.tabela.setRowCount(0)
        total = 0.0
        for despesa in despesas:
            total += despesa.valor
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            self.tabela.setItem(i, 0, celula(f"{despesa.data:%d/%m/%Y}"))
            self.tabela.setItem(
                i, 1, celula(despesa.descricao, despesa.observacao or despesa.descricao)
            )
            self.tabela.setItem(i, 2, celula(despesa.categoria_rotulo))
            valor = QTableWidgetItem(moeda(despesa.valor))
            valor.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabela.setItem(i, 3, valor)
            bt = QPushButton("Apagar")
            bt.setObjectName("perigo")
            bt.clicked.connect(lambda _, did=despesa.id: self._apagar(did))
            self.tabela.setCellWidget(i, 4, bt)

        self.rodape.setText(
            f"{len(despesas)} despesa(s) no período — total de {moeda(total)}."
            if despesas else "Nenhuma despesa lançada neste período."
        )

    def _apagar(self, despesa_id: int):
        from ..core.models import Despesa

        despesa = self.session.get(Despesa, despesa_id)
        if despesa is None:
            return
        if not confirmar(
            self, "Apagar despesa",
            f"Vou apagar “{despesa.descricao}” de {moeda(despesa.valor)}.\n\n"
            "Ela sai do balanço do período.",
            "Apagar",
        ):
            return
        try:
            financeiro.remover_despesa(self.session, despesa_id)
            self.session.commit()
        except financeiro.ErroFinanceiro as exc:
            self.session.rollback()
            avisar(self, "Não consegui apagar", str(exc))
            return
        self.recarregar()
