"""Janela principal — ESCOPO.md §6.

Tela inicial com quatro botões grandes e uma faixa de alertas que diz, em uma
frase, o que precisa de atenção hoje.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
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
    avisar,
    botao_cartao,
    confirmar,
    dica,
    faixa,
    informar,
    moeda,
    subtitulo,
    titulo,
)


class TelaInicial(QWidget):
    def __init__(self, janela):
        super().__init__(janela)
        self.janela = janela
        self.lay = QVBoxLayout(self)
        self.lay.setSpacing(16)
        self.lay.setContentsMargins(30, 24, 30, 24)

        self.lay.addWidget(titulo(APP_NAME))
        self.lay.addWidget(subtitulo("Controle de estoque da loja"))

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

        self.lb_mes = dica("")
        self.lay.addWidget(self.lb_mes)

        grade = QGridLayout()
        grade.setSpacing(16)
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
            grade.addWidget(b, i // 2, i % 2)
        self.lay.addLayout(grade)

        self.bt_kits = QPushButton("Configurar kits que faltam")
        self.bt_kits.clicked.connect(janela.abrir_kits)
        self.lay.addWidget(self.bt_kits)

        self.lay.addStretch(1)
        self.lay.addWidget(dica(f"Versão {__version__}"))
        self.recarregar()

    def _mostrar_mes(self, session) -> None:
        """Uma linha com o resultado do mês. Nunca bloqueia a tela se falhar."""
        try:
            b = financeiro.resumo_do_mes(session)
        except Exception:  # noqa: BLE001
            self.lb_mes.setText("")
            return
        if not b.tem_dados:
            self.lb_mes.setText("")
            return
        verbo = "sobraram" if b.lucro >= 0 else "faltaram"
        self.lb_mes.setText(
            f"Este mês: {b.vendas} venda(s) e {verbo} {moeda(abs(b.lucro))} "
            f"(margem {b.margem:.0f}%). Veja em Balanço."
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
        self.bt_kits.setVisible(bool(pendentes))
        if pendentes:
            self.bt_kits.setText(f"Configurar os {len(pendentes)} kits que faltam")


class JanelaPrincipal(QMainWindow):
    def __init__(self, session, verificar_atualizacao: bool = True):
        super().__init__()
        self.session = session
        self._verificador = None
        self.setWindowTitle(APP_NAME)
        self.resize(1080, 720)

        self.pilha = QStackedWidget()
        self.setCentralWidget(self.pilha)

        self.inicial = TelaInicial(self)
        self.estoque = TelaEstoque(session)
        self.kits_pendentes = TelaKitsPendentes(session)
        self.balanco = TelaBalanco(session)

        for tela in (self.inicial, self._com_voltar(self.estoque),
                     self._com_voltar(self.kits_pendentes),
                     self._com_voltar(self.balanco)):
            self.pilha.addWidget(tela)

        self._menu()
        self.statusBar().showMessage("Pronto")

        self.importando = False          # nunca atualizar no meio de uma importação
        self._atualizacao_pendente = None
        if verificar_atualizacao:
            self._verificar_atualizacao()

    def _com_voltar(self, conteudo: QWidget) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 16, 20, 16)
        topo = QHBoxLayout()
        bt = QPushButton("← Voltar")
        bt.clicked.connect(self.voltar_inicio)
        topo.addWidget(bt)
        topo.addStretch(1)
        lay.addLayout(topo)
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

    def voltar_inicio(self):
        self.inicial.recarregar()
        self.pilha.setCurrentIndex(0)

    def abrir_estoque(self):
        self.estoque.recarregar()
        self.pilha.setCurrentIndex(1)

    def abrir_kits(self):
        self.kits_pendentes.recarregar()
        self.pilha.setCurrentIndex(2)

    def abrir_balanco(self):
        self.balanco.recarregar()
        self.pilha.setCurrentIndex(3)

    # --------------------------------------------------------------- ações

    def abrir_entrada(self):
        if repo.contar(self.session)["simples"] == 0:
            informar(self, "Sem produtos ainda",
                     "Importe seu catálogo primeiro, em Arquivo → Importar catálogo.")
            return
        DialogoEntrada(self.session, self).exec()
        self.inicial.recarregar()
        self.estoque.recarregar()

    def abrir_ajuste(self):
        if repo.contar(self.session)["simples"] == 0:
            informar(self, "Sem produtos ainda",
                     "Importe seu catálogo primeiro, em Arquivo → Importar catálogo.")
            return
        DialogoAjuste(self.session, None, self).exec()
        self.inicial.recarregar()
        self.estoque.recarregar()

    def lancar_despesa(self):
        if DialogoDespesa(self.session, self).exec():
            self.balanco.recarregar()
            self.inicial.recarregar()

    def abrir_despesas(self):
        DialogoDespesas(self.session, pai=self).exec()
        self.balanco.recarregar()
        self.inicial.recarregar()

    def abrir_importacoes(self):
        DialogoImportacoes(self.session, self).exec()
        self.inicial.recarregar()
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
        self.inicial.recarregar()
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
        self.inicial.recarregar()
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
