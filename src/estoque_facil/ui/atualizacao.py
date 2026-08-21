"""Atualização pela interface — ESCOPO.md §10.2.

Regras respeitadas aqui:
  • nunca atualiza sozinho: sempre "Atualizar agora / Depois";
  • aviso discreto no topo, nunca popup no meio do trabalho;
  • nunca atualiza com importação em andamento;
  • o SHA256 é conferido antes de aplicar — não bateu, aborta.

O estoque não corre risco: os dados ficam em pasta própria do sistema, fora do
programa (§3.1), e a migração do banco roda com backup automático (core/migracoes).
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..services import updater
from ..version import __version__
from .widgets.comuns import avisar, dica, titulo

log = logging.getLogger(__name__)


class VerificadorDeVersao(QThread):
    """Consulta o GitHub em segundo plano. Sem internet, fica quieto."""

    encontrou = Signal(object)

    def run(self) -> None:
        try:
            self.encontrou.emit(updater.verificar())
        except Exception:  # noqa: BLE001
            log.exception("falha ao verificar atualização")
            self.encontrou.emit(None)


class _Baixador(QObject):
    progresso = Signal(int)
    pronto = Signal(object)
    falhou = Signal(str)

    def __init__(self, atualizacao):
        super().__init__()
        self.atualizacao = atualizacao

    def executar(self) -> None:
        try:
            caminho = updater.baixar(
                self.atualizacao, lambda f: self.progresso.emit(int(f * 100))
            )
            self.pronto.emit(caminho)
        except Exception as exc:  # noqa: BLE001
            log.exception("falha ao baixar atualização")
            self.falhou.emit(str(exc))


class DialogoAtualizacao(QDialog):
    def __init__(self, atualizacao, pai=None):
        super().__init__(pai)
        self.atualizacao = atualizacao
        self.setWindowTitle("Atualizar o Estoque Fácil")
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(titulo("Tem uma versão nova"))
        lay.addWidget(
            dica(f"Você tem a {__version__}. A mais nova é a {atualizacao.versao}.")
        )

        if atualizacao.notas:
            notas = QTextEdit(atualizacao.notas)
            notas.setReadOnly(True)
            notas.setMaximumHeight(160)
            lay.addWidget(notas)

        self.lb_status = QLabel(
            "Seu estoque não se perde: os dados ficam guardados fora do programa, "
            "e o app faz uma cópia de segurança antes de atualizar."
        )
        self.lb_status.setWordWrap(True)
        lay.addWidget(self.lb_status)

        self.barra = QProgressBar()
        self.barra.setVisible(False)
        lay.addWidget(self.barra)

        rodape = QHBoxLayout()
        rodape.addStretch(1)
        self.bt_depois = QPushButton("Depois")
        self.bt_depois.clicked.connect(self.reject)
        self.bt_agora = QPushButton("Atualizar agora")
        self.bt_agora.setObjectName("primario")
        self.bt_agora.clicked.connect(self._baixar)
        rodape.addWidget(self.bt_depois)
        rodape.addWidget(self.bt_agora)
        lay.addLayout(rodape)

        self._thread: QThread | None = None

    def _baixar(self) -> None:
        self.bt_agora.setEnabled(False)
        self.barra.setVisible(True)
        self.lb_status.setText("Baixando a nova versão…")

        self._thread = QThread(self)
        self._worker = _Baixador(self.atualizacao)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.executar)
        self._worker.progresso.connect(self.barra.setValue)
        self._worker.pronto.connect(self._aplicar)
        self._worker.falhou.connect(self._erro)
        self._thread.start()

    def _erro(self, mensagem: str) -> None:
        self.barra.setVisible(False)
        self.bt_agora.setEnabled(True)
        self.lb_status.setText("Não consegui baixar a atualização.")
        avisar(
            self,
            "Não consegui atualizar",
            "A atualização não foi aplicada e o app continua funcionando "
            "normalmente. Você pode tentar de novo depois.",
            detalhe_tecnico=mensagem,
        )

    def _aplicar(self, caminho) -> None:
        self.lb_status.setText("Abrindo o instalador. O app vai fechar.")
        try:
            updater.aplicar(caminho)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            self._erro(str(exc))
            return
        self.accept()
