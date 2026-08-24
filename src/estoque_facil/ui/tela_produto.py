"""Tela do produto, com o editor de composição — ESCOPO.md §5.2.1.

É a tela que ela vai abrir 75 vezes para configurar os kits, então tudo aqui é
otimizado para isso: sugestões prontas, conferência de custo automática e
"dá para montar" sempre visível.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core import kits, ledger, repo
from ..core.kits import ErroComposicao
from ..core.models import TipoMovimento, TipoProduto
from ..services import sugestao
from .dialogos import excluir_produto
from .widgets.comuns import (
    CampoDinheiro,
    avisar,
    confirmar,
    dica,
    faixa,
    informar,
    secao,
    titulo,
)

LARGURA_MAX_SUGESTAO = 26
MAX_SUGESTOES = 4
# A linha precisa caber um seletor de quantidade e um botão inteiros.
# Com 44px o seletor transbordava para a linha de baixo.
ALTURA_LINHA = 56
MAX_LINHAS_VISIVEIS = 5
COLUNAS_SUGESTAO = 2


class EditorComposicao(QWidget):
    """A lista 'Este kit é montado com' + sugestões + conferência de custo."""

    mudou = Signal()

    def __init__(self, session, produto, pai=None):
        super().__init__(pai)
        self.session = session
        self.produto = produto
        self._itens: dict[int, int] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(secao("Este kit é montado com:"))

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["Item", "Qtd", "Estoque", ""])
        self.tabela.verticalHeader().setVisible(False)
        # a linha precisa caber um seletor e um botão: 44px é o mínimo (§6)
        self.tabela.verticalHeader().setDefaultSectionSize(ALTURA_LINHA)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        for coluna, largura in ((1, 110), (2, 120), (3, 130)):
            cab.setSectionResizeMode(coluna, QHeaderView.Fixed)
            self.tabela.setColumnWidth(coluna, largura)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.tabela.setMinimumHeight(ALTURA_LINHA * 2)
        lay.addWidget(self.tabela)

        self.lb_custo = QLabel()
        self.lb_custo.setWordWrap(True)
        lay.addWidget(self.lb_custo)

        self.faixa_disp = faixa("", "ok")
        lay.addWidget(self.faixa_disp)

        lay.addWidget(dica("Sugestões — clique para adicionar:"))
        self.area_sugestoes = QWidget()
        self.lay_sugestoes = QGridLayout(self.area_sugestoes)
        self.lay_sugestoes.setContentsMargins(0, 0, 0, 0)
        self.lay_sugestoes.setSpacing(8)
        lay.addWidget(self.area_sugestoes)

        busca = QHBoxLayout()
        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText("Procurar outro item pelo nome ou código…")
        self.campo_busca.returnPressed.connect(self._buscar_e_adicionar)
        bt = QPushButton("Adicionar")
        bt.clicked.connect(self._buscar_e_adicionar)
        busca.addWidget(self.campo_busca, 1)
        busca.addWidget(bt)
        lay.addLayout(busca)

        self._carregar()

    # ------------------------------------------------------------------ dados

    def _carregar(self):
        self._itens = {
            c.componente_id: c.quantidade
            for c in kits.componentes_de(self.session, self.produto)
        }
        self._redesenhar()

    def itens(self) -> dict[int, int]:
        return dict(self._itens)

    def _adicionar(self, produto_id: int, quantidade: int = 1):
        comp = self.session.get(type(self.produto), produto_id)
        try:
            kits.validar_componente(self.produto, comp)
        except ErroComposicao as exc:
            avisar(self, "Não dá para adicionar este item", str(exc))
            return
        self._itens[produto_id] = self._itens.get(produto_id, 0) + quantidade
        self._redesenhar()

    def _buscar_e_adicionar(self):
        texto = self.campo_busca.text().strip()
        if not texto:
            return
        achados = [
            p for p in repo.buscar(self.session, texto, tipo=TipoProduto.SIMPLES)
            if p.id != self.produto.id
        ]
        if not achados:
            avisar(self, "Não encontrei", f"Nenhum item simples com “{texto}”.")
            return
        self._adicionar(achados[0].id)
        self.campo_busca.clear()

    # ---------------------------------------------------------------- desenho

    def _redesenhar(self):
        self.tabela.setRowCount(0)
        for pid, qtd in self._itens.items():
            comp = self.session.get(type(self.produto), pid)
            if comp is None:
                continue
            linha = self.tabela.rowCount()
            self.tabela.insertRow(linha)
            self.tabela.setItem(linha, 0, QTableWidgetItem(comp.rotulo))

            spin = QSpinBox()
            spin.setRange(1, 999)
            spin.setFixedHeight(38)
            spin.setValue(qtd)
            spin.valueChanged.connect(
                lambda v, p=pid: (self._itens.__setitem__(p, v), self._atualizar_resumos())
            )
            self.tabela.setCellWidget(linha, 1, spin)

            saldo = kits.disponivel(self.session, comp).quantidade
            item = QTableWidgetItem(f"{saldo}")
            if saldo <= 0:
                item.setForeground(Qt.red)
            self.tabela.setItem(linha, 2, item)

            remover = QPushButton("Remover")
            remover.setFixedHeight(38)
            remover.clicked.connect(lambda _, p=pid: self._remover(p))
            self.tabela.setCellWidget(linha, 3, remover)

        cabecalho = self.tabela.horizontalHeader().height() or 40
        visiveis = max(self.tabela.rowCount(), 1)
        altura = cabecalho + ALTURA_LINHA * min(visiveis, MAX_LINHAS_VISIVEIS) + 8
        self.tabela.setFixedHeight(altura)

        self._atualizar_sugestoes()
        self._atualizar_resumos()
        self.mudou.emit()

    def _remover(self, produto_id: int):
        self._itens.pop(produto_id, None)
        self._redesenhar()

    def _atualizar_sugestoes(self):
        while self.lay_sugestoes.count():
            item = self.lay_sugestoes.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        candidatos = [
            (score, p)
            for score, p in sugestao.sugerir_componentes(self.session, self.produto, 16)
            if p.id not in self._itens
        ][:MAX_SUGESTOES]
        for i, (_score, p) in enumerate(candidatos):
            rotulo = p.rotulo
            if len(rotulo) > LARGURA_MAX_SUGESTAO:
                rotulo = rotulo[: LARGURA_MAX_SUGESTAO - 1] + "…"
            b = QPushButton(f"+ {rotulo}")
            b.setToolTip(f"{p.rotulo}\n{p.sku} — R$ {p.custo:.2f}")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _, pid=p.id: self._adicionar(pid))
            self.lay_sugestoes.addWidget(b, i // COLUNAS_SUGESTAO, i % COLUNAS_SUGESTAO)
        if not candidatos:
            self.lay_sugestoes.addWidget(
                dica("Nenhuma sugestão — use a busca abaixo."), 0, 0
            )

    def _atualizar_resumos(self):
        soma = 0.0
        possiveis = []
        for pid, qtd in self._itens.items():
            comp = self.session.get(type(self.produto), pid)
            if comp is None:
                continue
            soma += comp.custo * qtd
            possiveis.append((kits.disponivel(self.session, comp).quantidade // qtd, comp))

        alvo = self.produto.custo
        if not self._itens:
            self.lb_custo.setText("")
        elif alvo:
            dif = round(soma - alvo, 2)
            if abs(dif) < 0.01:
                self.lb_custo.setText(
                    f"Soma dos itens: R$ {soma:.2f} — bate com o custo do kit."
                )
                self.lb_custo.setObjectName("ok")
            elif dif < 0:
                self.lb_custo.setText(
                    f"Soma dos itens: R$ {soma:.2f}. O kit custa R$ {alvo:.2f} — "
                    f"faltam R$ {-dif:.2f}. Esqueceu algum item?"
                )
                self.lb_custo.setObjectName("atencao")
            else:
                self.lb_custo.setText(
                    f"Soma dos itens: R$ {soma:.2f}. O kit custa R$ {alvo:.2f} — "
                    f"passou R$ {dif:.2f}. Confira as quantidades."
                )
                self.lb_custo.setObjectName("atencao")
        else:
            self.lb_custo.setText(f"Soma dos itens: R$ {soma:.2f}")
        self.lb_custo.style().polish(self.lb_custo)

        texto = "Adicione ao menos um item para saber quantos kits dá para montar."
        if possiveis:
            qtd, gargalo = min(possiveis, key=lambda p: p[0])
            texto = f"Dá para montar {max(qtd, 0)} — limitado por {gargalo.rotulo}."
        self.faixa_disp.atualizar(texto, "ok" if possiveis else "alerta")


class TelaProduto(QDialog):
    """Cadastro/edição de um produto, incluindo transformar em kit."""

    def __init__(self, session, produto=None, pai=None):
        super().__init__(pai)
        self.session = session
        self.produto = produto
        self.novo = produto is None
        self.editor: EditorComposicao | None = None

        self.setWindowTitle("Novo produto" if self.novo else produto.rotulo)

        # O diálogo nunca pode passar da tela: com o kit aberto ele fica alto, e
        # o rodapé com o Salvar precisa continuar visível.
        tela = QGuiApplication.primaryScreen().availableGeometry()
        self.setMinimumWidth(min(820, tela.width() - 80))
        self.resize(min(880, tela.width() - 60), min(760, tela.height() - 60))
        self.setMaximumHeight(tela.height() - 40)

        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        externo.addWidget(rolagem, 1)

        miolo = QWidget()
        rolagem.setWidget(miolo)
        lay = QVBoxLayout(miolo)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(titulo("Novo produto" if self.novo else produto.rotulo))

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.f_sku = QLineEdit(produto.sku if produto else "")
        self.f_nome = QLineEdit(produto.nome if produto else "")
        self.f_custo = CampoDinheiro()
        self.f_custo.setValue(produto.custo if produto else 0)
        self.f_minimo = QSpinBox()
        self.f_minimo.setRange(0, 99999)
        self.f_minimo.setValue(produto.estoque_minimo if produto else 0)
        self.f_local = QLineEdit(produto.localizacao if produto else "")
        self.f_obs = QTextEdit(produto.observacoes if produto else "")
        self.f_obs.setFixedHeight(64)

        for campo in (self.f_sku, self.f_nome, self.f_local):
            campo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            campo.setCursorPosition(0)   # nome longo abre pelo começo, não pelo meio
        for campo in (self.f_custo, self.f_minimo):
            campo.setFixedWidth(180)

        form.addRow("Código do produto", self.f_sku)
        form.addRow("Nome", self.f_nome)

        # custo e mínimo dividem a linha: economiza altura sem apertar nada
        numeros = QWidget()
        ln = QHBoxLayout(numeros)
        ln.setContentsMargins(0, 0, 0, 0)
        ln.setSpacing(10)
        ln.addWidget(self.f_custo)
        ln.addWidget(QLabel("Avisar com menos de"))
        ln.addWidget(self.f_minimo)
        ln.addStretch(1)
        form.addRow("Custo", numeros)
        lay.addLayout(form)

        # O que é opcional fica recolhido — a tela do kit precisa do espaço (§5.6)
        self.bt_mais = QPushButton("Mais opções ▾")
        self.bt_mais.setCheckable(True)
        self.bt_mais.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.bt_mais.toggled.connect(self._alternar_opcionais)
        lay.addWidget(self.bt_mais)

        self.area_opcionais = QWidget()
        opc = QFormLayout(self.area_opcionais)
        opc.setContentsMargins(0, 0, 0, 0)
        opc.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        opc.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        opc.addRow("Onde fica", self.f_local)
        opc.addRow("Observações", self.f_obs)
        self.area_opcionais.setVisible(False)
        lay.addWidget(self.area_opcionais)

        # estoque, só para itens simples
        self.linha_estoque = QWidget()
        le = QHBoxLayout(self.linha_estoque)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(QLabel("Quantidade em estoque"))
        self.f_estoque = QSpinBox()
        self.f_estoque.setRange(-99999, 999999)
        self.f_estoque.setFixedWidth(180)
        if produto and not produto.eh_kit:
            self.f_estoque.setValue(ledger.saldo_de(session, produto))
        le.addWidget(self.f_estoque)
        le.addStretch(1)
        lay.addWidget(self.linha_estoque)

        self.chk_kit = QCheckBox("Este produto é um kit (montado com outros itens)")
        self.chk_kit.setChecked(bool(produto and produto.eh_kit))
        self.chk_kit.toggled.connect(self._alternar_kit)
        lay.addWidget(self.chk_kit)

        self.area_kit = QWidget()
        self.lay_kit = QVBoxLayout(self.area_kit)
        self.lay_kit.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.area_kit)
        lay.addStretch(1)

        # rodapé FORA da rolagem: o Salvar fica sempre à vista
        barra = QFrame()
        barra.setObjectName("rodape")
        rodape = QHBoxLayout(barra)
        rodape.setContentsMargins(24, 12, 24, 12)
        if not self.novo:
            # Longe do Salvar, no canto oposto: é a ação que não se clica sem querer.
            self.bt_excluir = QPushButton("Excluir")
            self.bt_excluir.setObjectName("perigo")
            self.bt_excluir.clicked.connect(self._excluir)
            rodape.addWidget(self.bt_excluir)
        rodape.addStretch(1)
        bt_cancelar = QPushButton("Cancelar")
        bt_cancelar.clicked.connect(self.reject)
        self.bt_salvar = QPushButton("Salvar")
        self.bt_salvar.setObjectName("primario")
        self.bt_salvar.setDefault(True)
        self.bt_salvar.clicked.connect(self._salvar)
        rodape.addWidget(bt_cancelar)
        rodape.addWidget(self.bt_salvar)
        externo.addWidget(barra, 0)

        if produto and produto.eh_kit:
            self._montar_editor()
        self._sincronizar_visibilidade()

    def _alternar_opcionais(self, aberto: bool):
        self.area_opcionais.setVisible(aberto)
        self.bt_mais.setText("Menos opções ▴" if aberto else "Mais opções ▾")

    # ------------------------------------------------------------------ kit

    def _montar_editor(self):
        if self.editor is None and self.produto is not None:
            self.editor = EditorComposicao(self.session, self.produto)
            self.lay_kit.addWidget(self.editor)

    def _alternar_kit(self, marcado: bool):
        if marcado and self.produto is not None and not self.produto.eh_kit:
            pode, motivo = kits.pode_virar_kit(self.session, self.produto)
            if not pode:
                avisar(self, "Não dá para transformar em kit", motivo)
                self.chk_kit.setChecked(False)
                return
            saldo = ledger.saldo_de(self.session, self.produto)
            if saldo > 0 and not self._resolver_saldo_existente(saldo):
                self.chk_kit.setChecked(False)
                return
            self._montar_editor()
        elif marcado and self.produto is None:
            informar(
                self,
                "Salve o produto primeiro",
                "Para montar a composição eu preciso que o produto já exista.\n\n"
                "Salve agora e abra de novo para definir de que ele é montado.",
            )
        self._sincronizar_visibilidade()

    def _resolver_saldo_existente(self, saldo: int) -> bool:
        """§5.2.1 — kit não pode ter estoque próprio. Nunca descarta em silêncio."""
        return confirmar(
            self,
            "Este produto tem estoque",
            f"{self.produto.rotulo} tem {saldo} em estoque, mas um kit não guarda "
            "estoque próprio — ele é montado na hora a partir dos itens.\n\n"
            f"Vou zerar essas {saldo} unidades e registrar um ajuste no histórico. "
            "Se elas já estiverem montadas, desmonte antes de continuar.",
            "Zerar e continuar",
        )

    def _sincronizar_visibilidade(self):
        eh_kit = self.chk_kit.isChecked()
        self.area_kit.setVisible(eh_kit and self.editor is not None)
        self.linha_estoque.setVisible(not eh_kit)
        if eh_kit:
            self.f_custo.setToolTip(
                "O custo do kit é usado para conferir se a composição está completa."
            )

    # -------------------------------------------------------------- excluir

    def _excluir(self):
        """Sai pelo `accept()` para a lista de trás recarregar — o produto mudou."""
        if excluir_produto(self, self.session, self.produto):
            self.accept()

    # --------------------------------------------------------------- salvar

    def _salvar(self):
        sku = self.f_sku.text().strip()
        if not sku:
            avisar(self, "Falta o código", "Todo produto precisa de um código.")
            return

        eh_kit = self.chk_kit.isChecked()
        try:
            if self.novo:
                self.produto = repo.criar_produto(
                    self.session, sku, self.f_nome.text().strip(),
                    tipo=TipoProduto.KIT if eh_kit else TipoProduto.SIMPLES,
                    custo=self.f_custo.value(), estoque_minimo=self.f_minimo.value(),
                )
            else:
                self.produto.sku = sku
                from ..core.models import normalizar_sku

                self.produto.sku_norm = normalizar_sku(sku)
                self.produto.nome = self.f_nome.text().strip()
                self.produto.custo = self.f_custo.value()
                self.produto.estoque_minimo = self.f_minimo.value()
            self.produto.localizacao = self.f_local.text().strip() or None
            self.produto.observacoes = self.f_obs.toPlainText().strip() or None

            if eh_kit:
                if self.editor is None:
                    self.produto.tipo = TipoProduto.KIT
                else:
                    saldo = ledger.saldo_de(self.session, self.produto) \
                        if not self.produto.eh_kit else 0
                    if saldo:
                        ledger.ajustar(
                            self.session, self.produto, 0,
                            tipo=TipoMovimento.DESMONTAGEM,
                            observacao="Zerado ao transformar em kit",
                        )
                    kits.definir_composicao(self.session, self.produto, self.editor.itens())
            else:
                if self.produto.eh_kit:
                    for c in kits.componentes_de(self.session, self.produto):
                        self.session.delete(c)
                self.produto.tipo = TipoProduto.SIMPLES
                self.session.flush()
                ledger.ajustar(
                    self.session, self.produto, self.f_estoque.value(),
                    tipo=TipoMovimento.AJUSTE, observacao="Ajuste pela tela do produto",
                )

            self.session.commit()
        except (ErroComposicao, ledger.ErroEstoque, ValueError) as exc:
            self.session.rollback()
            avisar(self, "Não consegui salvar", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            avisar(self, "Não consegui salvar", "Algo deu errado ao gravar.",
                   detalhe_tecnico=repr(exc))
            return

        self.accept()
