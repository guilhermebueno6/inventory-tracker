"""Janela principal — ESCOPO.md §6 e manual da marca §05.

Tela inicial com os botões grandes e uma faixa de alertas que diz, em uma
frase, o que precisa de atenção hoje.

O que a marca acrescentou: a barra de título fixa no topo (símbolo + wordmark
à esquerda, navegação em rótulos caixa alta à direita), que substituiu o botão
"← Voltar" que cada tela carregava. Com a navegação sempre visível, sair de uma
tela deixou de depender de achar um botão dentro dela.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import kits, ledger, repo
from ..services import backup, financeiro, importacao
from ..version import APP_NAME, __version__
from . import marca
from .atualizacao import DialogoAtualizacao, VerificadorDeVersao
from .dialogos import (
    DialogoAjuste,
    DialogoDespesa,
    DialogoDespesas,
    DialogoEntrada,
    DialogoImportacoes,
)
from .tela_balanco import TelaBalanco
from .tela_estoque import TelaEstoque
from .tela_importacao import TelaImportacao, escolher_arquivo
from .tela_kits import TelaKitsPendentes
from .widgets.comuns import (
    Lockup,
    avisar,
    botao_cartao,
    botao_nav,
    confirmar,
    dica,
    faixa,
    informar,
    marcar_ativo,
    moeda,
    numero_grande,
    regua,
    rotulo,
)

# Índices da pilha de telas. Nomeados porque a barra de navegação e os métodos
# de abrir/voltar precisam falar da mesma tela sem número solto no meio do código.
INICIO, ESTOQUE, KITS, BALANCO = range(4)


class BarraDeTitulo(QFrame):
    """Barra fixa do topo — manual §05.

    Símbolo a 22 px + wordmark à esquerda; navegação em rótulos caixa alta à
    direita, com régua vermelha de 2px embaixo do item atual.
    """

    def __init__(self, janela: JanelaPrincipal):
        super().__init__(janela)
        self.setObjectName("barraTitulo")
        self.setFixedHeight(64)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(30, 0, 30, 0)
        lay.setSpacing(0)

        self.lockup = Lockup(22)
        self.lockup.setCursor(Qt.PointingHandCursor)
        self.lockup.setToolTip("Voltar para o início")
        self.lockup.clicado.connect(janela.voltar_inicio)
        lay.addWidget(self.lockup)
        lay.addStretch(1)

        self.itens: dict[int, QPushButton] = {}
        for indice, texto, acao in (
            (INICIO, "Início", janela.voltar_inicio),
            (ESTOQUE, "Estoque", janela.abrir_estoque),
            (KITS, "Kits", janela.abrir_kits),
            (BALANCO, "Balanço", janela.abrir_balanco),
        ):
            b = botao_nav(texto, ativo=indice == INICIO)
            b.clicked.connect(acao)
            lay.addWidget(b)
            self.itens[indice] = b

    def marcar(self, indice: int) -> None:
        for i, botao in self.itens.items():
            marcar_ativo(botao, i == indice)

    def mostrar_kits(self, visivel: bool) -> None:
        """A aba de kits só existe enquanto houver kit pendente."""
        self.itens[KITS].setVisible(visivel)


class TelaInicial(QWidget):
    def __init__(self, janela):
        super().__init__(janela)
        self.janela = janela
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(14)
        self.lay.setContentsMargins(30, 26, 30, 24)

        cabecalho = QHBoxLayout()
        cabecalho.addWidget(Lockup(46, assinatura=True))
        cabecalho.addStretch(1)
        self.lay.addLayout(cabecalho)
        self.lay.addWidget(regua())
        self.lay.addSpacing(4)

        # Aviso discreto e não bloqueante, no topo — nunca popup (§10.2)
        self.barra_atualizacao = QWidget()
        ba = QHBoxLayout(self.barra_atualizacao)
        ba.setContentsMargins(0, 0, 0, 0)
        self.lb_atualizacao = QLabel("")
        self.lb_atualizacao.setWordWrap(True)
        bt_atualizar = QPushButton("Ver a novidade")
        bt_atualizar.clicked.connect(janela.abrir_atualizacao)
        ba.addWidget(self.lb_atualizacao, 1)
        ba.addWidget(bt_atualizar)
        self.barra_atualizacao.setVisible(False)
        self.lay.addWidget(self.barra_atualizacao)

        self.faixa_alerta = faixa("")
        self.lay.addWidget(self.faixa_alerta)

        self.lay.addWidget(self._bloco_do_mes())

        grade = QGridLayout()
        grade.setSpacing(14)
        botoes = [
            ("Ver estoque", "o que tem e o que está acabando", janela.abrir_estoque),
            ("Importar vendas", "baixar o relatório do Mercado Livre", janela.importar_vendas),
            ("Entrada de mercadoria", "registrar o que chegou", janela.abrir_entrada),
            ("Lançar despesa", "o que você gastou com a loja", janela.lancar_despesa),
            ("Balanço", "quanto sobrou no mês", janela.abrir_balanco),
            ("Backup", "guardar uma cópia dos seus dados", janela.fazer_backup),
        ]
        for i, (texto, desc, acao) in enumerate(botoes):
            b = botao_cartao(texto, desc)
            b.clicked.connect(acao)
            grade.addWidget(b, i // 3, i % 3)
        for coluna in range(3):
            grade.setColumnStretch(coluna, 1)
        self.lay.addLayout(grade)

        self.bt_kits = QPushButton("Configurar kits que faltam")
        self.bt_kits.clicked.connect(janela.abrir_kits)
        rodape_kits = QHBoxLayout()
        rodape_kits.addWidget(self.bt_kits)
        rodape_kits.addStretch(1)
        self.lay.addLayout(rodape_kits)

        self.lay.addStretch(1)
        self.lay.addWidget(regua(clara=True))
        self.lay.addWidget(dica(f"Versão {__version__}"))

        # Estado do DADO, não do widget: quem pergunta "tem kit pendente?" pode
        # estar com esta tela fora da pilha, e aí `bt_kits.isVisible()` mente.
        self.tem_kits_pendentes = False
        self.recarregar()

    def _bloco_do_mes(self) -> QFrame:
        """O resultado do mês como "Número" do manual §04: 34, peso 700, tabular.

        É o dado que ela abre o app para ver. Antes era uma linha de texto
        pequeno no meio da tela, do mesmo tamanho de tudo o que estava em volta.
        """
        bloco = QFrame()
        bloco.setObjectName("cartaoInfo")
        lay = QVBoxLayout(bloco)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(4)

        self.lb_rotulo_mes = rotulo("Resultado deste mês")
        lay.addWidget(self.lb_rotulo_mes)

        self.lb_valor_mes = numero_grande("—")
        lay.addWidget(self.lb_valor_mes)

        self.lb_mes = dica("")
        lay.addWidget(self.lb_mes)

        self.bloco_mes = bloco
        return bloco

    def _mostrar_mes(self, session) -> None:
        """Uma linha com o resultado do mês. Nunca bloqueia a tela se falhar."""
        try:
            b = financeiro.resumo_do_mes(session)
        except Exception:  # noqa: BLE001
            self.bloco_mes.setVisible(False)
            self.lb_mes.setText("")
            return
        if not b.tem_dados:
            self.bloco_mes.setVisible(False)
            self.lb_mes.setText("")
            return

        self.bloco_mes.setVisible(True)
        negativo = b.lucro < 0
        self.lb_valor_mes.setText(moeda(b.lucro))
        # a cor sai do objectName, e o QSS precisa ser reaplicado para pegar
        self.lb_valor_mes.setObjectName("numeroNegativo" if negativo else "numero")
        self.lb_valor_mes.style().unpolish(self.lb_valor_mes)
        self.lb_valor_mes.style().polish(self.lb_valor_mes)

        verbo = "sobraram" if not negativo else "faltaram"
        self.lb_mes.setText(
            f"{b.vendas} venda(s) neste mês e {verbo} {moeda(abs(b.lucro))} "
            f"— margem de {b.margem:.0f}%. Veja em Balanço."
        )

    def mostrar_atualizacao(self, atualizacao) -> None:
        self.lb_atualizacao.setText(
            f"Tem uma versão nova ({atualizacao.versao}). Seu estoque não se perde."
        )
        self.barra_atualizacao.setVisible(True)

    def recarregar(self):
        session = self.janela.session
        pendentes = kits.kits_sem_composicao(session)
        alertas = repo.abaixo_do_minimo(session)
        contagem = repo.contar(session)

        if contagem["total"] == 0:
            texto, tipo = (
                "Comece importando seu catálogo em Arquivo → Importar catálogo (CSV).",
                "alerta",
            )
        elif pendentes:
            texto, tipo = (
                f"{len(pendentes)} de {contagem['kits']} kits ainda não sabem de que "
                "são montados. Enquanto isso, as vendas desses kits não baixam estoque.",
                "alerta",
            )
        elif alertas:
            travados = sum(len(k) for _p, _q, k in alertas)
            texto = f"{len(alertas)} itens estão acabando"
            if travados:
                texto += f" — isso trava {travados} kit(s)"
            texto += "."
            tipo = "alerta"
        else:
            texto, tipo = ("Tudo em ordem. Nenhum item abaixo do mínimo.", "ok")

        self.faixa_alerta.atualizar(texto, tipo)
        self._mostrar_mes(session)
        self.tem_kits_pendentes = bool(pendentes)
        self.bt_kits.setVisible(self.tem_kits_pendentes)
        if pendentes:
            self.bt_kits.setText(f"Configurar os {len(pendentes)} kits que faltam")


class JanelaPrincipal(QMainWindow):
    def __init__(self, session, verificar_atualizacao: bool = True):
        super().__init__()
        self.session = session
        self._verificador = None
        self.setWindowTitle(APP_NAME)
        self.resize(1080, 720)

        self.setWindowIcon(marca.icone_do_app())

        self.pilha = QStackedWidget()
        self.inicial = TelaInicial(self)
        self.estoque = TelaEstoque(session)
        self.kits_pendentes = TelaKitsPendentes(session)
        self.balanco = TelaBalanco(session)

        for tela in (self.inicial, self._com_margem(self.estoque),
                     self._com_margem(self.kits_pendentes),
                     self._com_margem(self.balanco)):
            self.pilha.addWidget(tela)

        # A barra vem antes da pilha e nunca sai da tela: é o chrome do app.
        self.barra = BarraDeTitulo(self)
        corpo = QWidget()
        lay_corpo = QVBoxLayout(corpo)
        lay_corpo.setContentsMargins(0, 0, 0, 0)
        lay_corpo.setSpacing(0)
        lay_corpo.addWidget(self.barra)
        lay_corpo.addWidget(self.pilha, 1)
        self.setCentralWidget(corpo)

        self._menu()
        # A barra nasce com todos os itens; sem isto a aba de Kits aparece na
        # abertura mesmo para quem já configurou todos os kits.
        self._atualizar_navegacao(INICIO)
        self.statusBar().showMessage("Pronto")

        self.importando = False          # nunca atualizar no meio de uma importação
        self._atualizacao_pendente = None
        if verificar_atualizacao:
            self._verificar_atualizacao()

    def _com_margem(self, conteudo: QWidget) -> QWidget:
        """Só o respiro da página: quem navega agora é a barra de título."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 22, 30, 22)
        lay.addWidget(conteudo, 1)
        return w

    def _menu(self):
        arquivo = self.menuBar().addMenu("Arquivo")
        arquivo.addAction("Importar catálogo (CSV)…", self.importar_catalogo)
        arquivo.addAction("Preencher nomes pelo relatório do ML…", self.preencher_nomes)
        arquivo.addSeparator()
        arquivo.addAction("Fazer backup agora…", self.fazer_backup)
        arquivo.addSeparator()
        arquivo.addAction("Sair", self.close)

        vendas = self.menuBar().addMenu("Vendas")
        vendas.addAction("Importar vendas…", self.importar_vendas)
        vendas.addAction("Ver importações / desfazer…", self.abrir_importacoes)

        dinheiro = self.menuBar().addMenu("Dinheiro")
        dinheiro.addAction("Balanço do período…", self.abrir_balanco)
        dinheiro.addAction("Lançar despesa…", self.lancar_despesa)
        dinheiro.addAction("Ver despesas…", self.abrir_despesas)

        ferramentas = self.menuBar().addMenu("Ferramentas")
        ferramentas.addAction("Ajuste de estoque (perda, quebra)…", self.abrir_ajuste)
        ferramentas.addAction("Conferir estoque (recalcular)", self.recalcular)

        ajuda = self.menuBar().addMenu("Ajuda")
        ajuda.addAction("Buscar atualizações…", lambda: self._verificar_atualizacao(True))
        ajuda.addAction("Onde ficam meus dados…", self.mostrar_pasta_dados)

    # ------------------------------------------------------------ navegação

    def _atualizar_navegacao(self, indice: int | None = None) -> None:
        """Liga/desliga a aba de Kits a partir do dado.

        Antes isto perguntava `self.inicial.bt_kits.isVisible()`. Como a tela
        inicial fica escondida enquanto outra tela está na pilha, a resposta era
        sempre "não" ao voltar de qualquer tela — a aba sumia e nunca mais
        voltava. A aba nunca é escondida debaixo de quem está nela.
        """
        if indice is None:
            indice = self.pilha.currentIndex()
        self.barra.mostrar_kits(self.inicial.tem_kits_pendentes or indice == KITS)

    def _recarregar_inicial(self) -> None:
        """Recarrega a tela inicial e deixa a navegação de acordo com ela."""
        self.inicial.recarregar()
        self._atualizar_navegacao()

    def _ir_para(self, indice: int) -> None:
        self.pilha.setCurrentIndex(indice)
        self.barra.marcar(indice)
        self._atualizar_navegacao(indice)

    def voltar_inicio(self):
        self.inicial.recarregar()
        self._ir_para(INICIO)

    def abrir_estoque(self):
        self.estoque.recarregar()
        self._ir_para(ESTOQUE)

    def abrir_kits(self):
        self.kits_pendentes.recarregar()
        self._ir_para(KITS)

    def abrir_balanco(self):
        self.balanco.recarregar()
        self._ir_para(BALANCO)

    # --------------------------------------------------------------- ações

    def abrir_entrada(self):
        if repo.contar(self.session)["simples"] == 0:
            informar(self, "Sem produtos ainda",
                     "Importe seu catálogo primeiro, em Arquivo → Importar catálogo.")
            return
        DialogoEntrada(self.session, self).exec()
        self._recarregar_inicial()
        self.estoque.recarregar()

    def abrir_ajuste(self):
        if repo.contar(self.session)["simples"] == 0:
            informar(self, "Sem produtos ainda",
                     "Importe seu catálogo primeiro, em Arquivo → Importar catálogo.")
            return
        DialogoAjuste(self.session, None, self).exec()
        self._recarregar_inicial()
        self.estoque.recarregar()

    def lancar_despesa(self):
        if DialogoDespesa(self.session, self).exec():
            self.balanco.recarregar()
            self._recarregar_inicial()

    def abrir_despesas(self):
        DialogoDespesas(self.session, pai=self).exec()
        self.balanco.recarregar()
        self._recarregar_inicial()

    def abrir_importacoes(self):
        DialogoImportacoes(self.session, self).exec()
        self._recarregar_inicial()
        self.estoque.recarregar()

    def importar_vendas(self):
        caminho = escolher_arquivo(self)
        if not caminho:
            return
        self.importando = True          # trava a atualização enquanto isto roda
        try:
            aplicou = tela_exec = TelaImportacao(self.session, caminho, self)
            aplicou = tela_exec.exec()
        finally:
            self.importando = False
        tela = tela_exec
        if aplicou and tela.resumo_final:
            r = tela.resumo_final
            extra = ""
            if r.linhas_corrigidas:
                extra = (
                    f"\n{r.linhas_corrigidas} venda(s) que já estavam aqui foram "
                    "atualizadas (cancelamento ou devolução no relatório novo)."
                )
            informar(
                self, "Baixa concluída",
                f"{r.vendas_aplicadas} vendas lançadas, {r.movimentos} movimentos "
                f"de estoque.\n{r.linhas_financeiras} linha(s) entraram no balanço."
                f"{extra}\n\nSe algo saiu errado, use Vendas → Ver importações "
                "para desfazer.",
            )
        self._recarregar_inicial()
        self.estoque.recarregar()
        self.kits_pendentes.recarregar()
        self.balanco.recarregar()

    def importar_catalogo(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolha o arquivo do catálogo", "",
            "Planilhas (*.csv *.txt);;Todos os arquivos (*)",
        )
        if not caminho:
            return
        try:
            resumo = importacao.importar_catalogo(self.session, Path(caminho))
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            avisar(self, "Não consegui importar o catálogo", str(exc),
                   detalhe_tecnico=repr(exc))
            return
        informar(
            self, "Catálogo importado",
            f"{resumo.criados} produtos criados, {resumo.atualizados} atualizados.\n"
            f"{resumo.kits_marcados} foram marcados como kit — confira se está certo "
            "e depois monte a composição de cada um.",
        )
        self._recarregar_inicial()
        self.estoque.recarregar()
        self.kits_pendentes.recarregar()

    def preencher_nomes(self):
        caminho = escolher_arquivo(self)
        if not caminho:
            return
        try:
            n = importacao.preencher_nomes(self.session, caminho)
            self.session.commit()
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            avisar(self, "Não consegui ler o relatório", str(exc), detalhe_tecnico=repr(exc))
            return
        informar(self, "Nomes preenchidos",
                 f"{n} produtos ganharam nome a partir do relatório.\n\n"
                 "Quanto maior o período do relatório, mais produtos ficam com nome.")
        self.estoque.recarregar()

    def fazer_backup(self):
        destino, _ = QFileDialog.getSaveFileName(
            self, "Onde salvar o backup", "backup-estoque.zip", "Arquivo ZIP (*.zip)"
        )
        if not destino:
            return
        try:
            caminho = backup.gerar_zip(self.session, Path(destino))
        except Exception as exc:  # noqa: BLE001
            avisar(self, "Não consegui salvar o backup", str(exc), detalhe_tecnico=repr(exc))
            return
        informar(self, "Backup pronto",
                 f"Salvo em:\n{caminho}\n\nGuarde esse arquivo em outro lugar — "
                 "pen drive, e-mail ou Google Drive.")

    def recalcular(self):
        problemas = ledger.verificar_invariante(self.session)
        if not problemas:
            informar(self, "Está tudo certo",
                     "Conferi o estoque contra todo o histórico e os números batem.")
            return
        if confirmar(
            self, "Encontrei diferenças",
            f"{len(problemas)} produtos estão com o número diferente do histórico.\n\n"
            "Posso recalcular a partir do histórico, que é a fonte confiável.",
            "Recalcular",
        ):
            ledger.recalcular_saldos(self.session)
            self.session.commit()
            informar(self, "Pronto", "Estoque recalculado.")
            self.estoque.recarregar()

    # ------------------------------------------------------- atualização

    def _verificar_atualizacao(self, manual: bool = False) -> None:
        self._verificador = VerificadorDeVersao(self)
        self._verificador.encontrou.connect(
            lambda a: self._resultado_atualizacao(a, manual)
        )
        self._verificador.start()

    def _resultado_atualizacao(self, atualizacao, manual: bool) -> None:
        if atualizacao is None:
            if manual:
                informar(
                    self, "Tudo em dia",
                    f"Você já está na versão mais nova ({__version__}).",
                )
            return
        self._atualizacao_pendente = atualizacao
        self.inicial.mostrar_atualizacao(atualizacao)
        if manual:
            self.abrir_atualizacao()

    def abrir_atualizacao(self) -> None:
        if self._atualizacao_pendente is None:
            return
        if self.importando:
            informar(
                self, "Termine a importação primeiro",
                "Você está no meio de uma importação de vendas. "
                "Conclua ou cancele antes de atualizar.",
            )
            return
        DialogoAtualizacao(self._atualizacao_pendente, self).exec()

    def mostrar_pasta_dados(self) -> None:
        from ..core.db import pasta_dados

        informar(
            self, "Onde ficam seus dados",
            "Seu estoque fica guardado nesta pasta, FORA do programa:\n\n"
            f"{pasta_dados()}\n\n"
            "Por isso desinstalar ou atualizar o aplicativo não apaga nada. "
            "Os backups automáticos ficam na subpasta 'backups'.",
        )

    def _parar_verificador(self) -> None:
        """Encerra a checagem de versão antes de fechar.

        Sem isto, fechar a janela enquanto a consulta ao GitHub ainda está no ar
        destrói uma QThread em execução — e o Qt aborta o processo. Aparece como
        um fechamento "com erro" para quem está usando.
        """
        t = self._verificador
        if t is not None and t.isRunning():
            t.requestInterruption()
            t.quit()
            t.wait(3000)

    def closeEvent(self, evento):
        """Backup silencioso ao fechar (§7.1)."""
        self._parar_verificador()
        try:
            backup.gerar(self.session, incluir_db=True)
            backup.limpar_antigos()
        except Exception:  # noqa: BLE001, S110
            pass
        self.session.close()
        super().closeEvent(evento)
