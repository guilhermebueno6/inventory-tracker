"""Tela de conferência da importação — ESCOPO.md §5.1.

É a tela que impede baixa errada: nada é gravado até ela clicar em confirmar.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import repo
from ..core.models import TipoProduto
from ..importers.ml_vendas_xlsx import ErroArquivoML
from ..services import importacao
from ..services.importacao import Situacao
from . import marca
from .tela_produto import TelaProduto
from .widgets.comuns import (
    avisar,
    celula,
    celula_numero,
    configurar_colunas,
    confirmar,
    dica,
    faixa,
    informar,
    regua,
    titulo,
)

# Paleta mono (manual §03). O que separa as situações aqui é a aba em que a
# linha está, não a cor: só o que exige ação da usuária ganha vermelho.
CORES = {
    Situacao.PRONTA: QColor(marca.TINTA),
    Situacao.ATENCAO: QColor(marca.CINZA),
    Situacao.SEM_CADASTRO: QColor(marca.VERMELHO_ESCURO),
    Situacao.JA_PROCESSADA: QColor(marca.DESABILITADO),
    Situacao.NAO_ABATE: QColor(marca.DESABILITADO),
}
TITULOS = {
    Situacao.PRONTA: "Prontas",
    Situacao.ATENCAO: "Atenção",
    Situacao.SEM_CADASTRO: "Sem cadastro",
    Situacao.NAO_ABATE: "Não baixam estoque",
    Situacao.JA_PROCESSADA: "Já importadas",
}


def escolher_arquivo(pai) -> Path | None:
    caminho, _ = QFileDialog.getOpenFileName(
        pai, "Escolha o relatório de vendas do Mercado Livre", "",
        "Planilhas (*.xlsx *.xls);;Todos os arquivos (*)",
    )
    return Path(caminho) if caminho else None


class TelaImportacao(QDialog):
    def __init__(self, session, caminho: Path, pai=None):
        super().__init__(pai)
        self.session = session
        self.caminho = Path(caminho)
        self.analise = None
        self.resumo_final = None

        self.setWindowTitle("Conferir vendas antes de baixar")
        tela = QGuiApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(980, tela.width() - 80), min(600, tela.height() - 80))
        self.resize(min(1160, tela.width() - 60), min(720, tela.height() - 60))

        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(12)
        self.lay.addWidget(titulo("Conferir vendas"))
        self.lay.addWidget(regua())
        self.lb_arquivo = dica(f"Arquivo: {self.caminho.name}")
        self.lay.addWidget(self.lb_arquivo)

        self.faixa_resumo = faixa("Lendo o arquivo…")
        self.lay.addWidget(self.faixa_resumo)

        self.abas = QTabWidget()
        self.lay.addWidget(self.abas, 1)

        rodape = QHBoxLayout()
        self.lb_aviso = QLabel("")
        self.lb_aviso.setWordWrap(True)
        rodape.addWidget(self.lb_aviso, 1)
        bt_cancelar = QPushButton("Cancelar")
        bt_cancelar.clicked.connect(self.reject)
        self.bt_confirmar = QPushButton("Confirmar baixa")
        self.bt_confirmar.setObjectName("primario")
        self.bt_confirmar.clicked.connect(self._confirmar)
        rodape.addWidget(bt_cancelar)
        rodape.addWidget(self.bt_confirmar)
        self.lay.addLayout(rodape)

        self._analisar()

    # --------------------------------------------------------------- análise

    def _analisar(self):
        try:
            self.analise = importacao.analisar_vendas(self.session, self.caminho)
        except ErroArquivoML as exc:
            avisar(self, "Não consegui ler este arquivo", str(exc))
            self.reject()
            return
        except Exception as exc:  # noqa: BLE001
            avisar(self, "Não consegui ler este arquivo",
                   "Algo deu errado ao abrir a planilha.", detalhe_tecnico=repr(exc))
            self.reject()
            return
        self._desenhar()

    def _trocar_faixa(self, texto: str, tipo: str):
        self.faixa_resumo.atualizar(texto, tipo)

    def _desenhar(self):
        a = self.analise
        rel = a.relatorio
        periodo = ""
        if rel.periodo_inicio and rel.periodo_fim:
            periodo = (f"  Período: {rel.periodo_inicio:%d/%m/%Y} a "
                       f"{rel.periodo_fim:%d/%m/%Y}.")
        self._trocar_faixa(
            a.resumo() + periodo, "ok" if not a.por(Situacao.SEM_CADASTRO) else "alerta"
        )

        self.abas.clear()
        ordem = [Situacao.PRONTA, Situacao.ATENCAO, Situacao.SEM_CADASTRO,
                 Situacao.NAO_ABATE, Situacao.JA_PROCESSADA]
        for situacao in ordem:
            linhas = a.por(situacao)
            if not linhas:
                continue
            self.abas.addTab(self._aba(linhas, situacao),
                             f"{TITULOS[situacao]} ({len(linhas)})")

        pendentes = len(a.por(Situacao.SEM_CADASTRO))
        self.bt_confirmar.setEnabled(bool(a.aplicaveis))
        if pendentes:
            quantas = (
                f"{pendentes} linhas não vão entrar" if pendentes > 1
                else "1 linha não vai entrar"
            )
            self.lb_aviso.setText(
                f"{quantas}. Você pode resolver agora ou confirmar o resto e "
                "cuidar delas depois."
            )
        elif not a.aplicaveis:
            self.lb_aviso.setText("Nada novo para importar neste arquivo.")
        else:
            self.lb_aviso.setText("")

    def _aba(self, linhas, situacao) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tabela = QTableWidget(0, 5)
        tabela.setHorizontalHeaderLabels(
            ["Venda", "Produto", "Qtd", "O que vai acontecer", "Observação"]
        )
        tabela.verticalHeader().setVisible(False)
        tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        tabela.setSelectionBehavior(QTableWidget.SelectRows)
        tabela.verticalHeader().setDefaultSectionSize(38)
        # "O que vai acontecer" é a coluna que dá confiança: é ela que estica
        configurar_colunas(tabela, [215, 240, "auto", None, 200])

        for linha in linhas:
            i = tabela.rowCount()
            tabela.insertRow(i)
            tabela.setItem(i, 0, celula(linha.origem.numero_venda))
            tabela.setItem(i, 1, celula(linha.descricao))
            tabela.setItem(i, 2, celula_numero(str(linha.origem.quantidade)))

            if linha.baixas:
                detalhe = ", ".join(f"−{q} {p.rotulo}" for p, q in linha.baixas)
                if linha.produto and linha.produto.eh_kit:
                    detalhe = f"Kit → {detalhe}"
            else:
                detalhe = "—"
            tabela.setItem(i, 3, celula(detalhe))

            obs = celula(linha.motivo)
            obs.setForeground(QBrush(CORES[situacao]))
            tabela.setItem(i, 4, obs)
            tabela.item(i, 0).setData(Qt.UserRole, linha.origem.sku)

        lay.addWidget(tabela, 1)

        if situacao == Situacao.SEM_CADASTRO:
            acoes = QHBoxLayout()
            bt_criar = QPushButton("Cadastrar este produto")
            bt_criar.clicked.connect(lambda: self._resolver(tabela, linhas))
            acoes.addWidget(bt_criar)
            acoes.addStretch(1)
            acoes.addWidget(dica("Escolha uma linha e resolva sem sair desta tela."))
            lay.addLayout(acoes)
        return w

    def _resolver(self, tabela, linhas):
        i = tabela.currentRow()
        if i < 0:
            informar(self, "Escolha uma linha", "Clique na linha que você quer resolver.")
            return
        linha = linhas[i]
        produto = linha.produto
        if produto is None:
            from ..importers.catalogo_csv import parece_kit

            eh_kit = parece_kit(linha.origem.sku, linha.origem.titulo)
            try:
                produto = repo.criar_produto(
                    self.session,
                    linha.origem.sku,
                    linha.origem.titulo,
                    tipo=TipoProduto.KIT if eh_kit else TipoProduto.SIMPLES,
                    ml_item_id=linha.origem.mlb or None,
                    variacao=linha.origem.variacao or None,
                )
                self.session.commit()
            except ValueError as exc:
                avisar(self, "Não consegui cadastrar", str(exc))
                return
        if TelaProduto(self.session, produto, self).exec():
            self._analisar()

    # ------------------------------------------------------------- confirmar

    def _confirmar(self):
        a = self.analise
        if not confirmar(
            self,
            "Confirmar baixa",
            f"Você vai dar baixa de {a.unidades_a_baixar} unidades em "
            f"{a.produtos_afetados} produtos, a partir de {len(a.aplicaveis)} vendas.\n\n"
            "Isso pode ser desfeito depois.",
            "Dar baixa",
        ):
            return
        try:
            self.resumo_final = importacao.confirmar_vendas(self.session, a)
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            avisar(self, "Não consegui gravar",
                   "Nada foi alterado no estoque.", detalhe_tecnico=repr(exc))
            return
        self.accept()
