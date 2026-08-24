"""Aplicação do tema da marca no QApplication.

Um lugar só para as três coisas que precisam acontecer antes da primeira
janela aparecer: registrar o Archivo, vestir o app com a folha de estilo e
pendurar o ícone. Fica separado do `marca.py` porque aqui já se mexe no
QApplication — o `marca.py` continua sendo só a fonte dos tokens.
"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from . import marca


def vestir(app: QApplication) -> None:
    """Carrega a fonte, aplica o QSS e define o ícone do aplicativo."""
    familia = marca.carregar_fontes()

    # A fonte também vai no QApplication, e não só no QSS: o que é pintado à
    # mão (o lockup, os itens de tabela) não passa pela folha de estilo.
    fonte = app.font()
    fonte.setFamily(familia)
    fonte.setPointSize(marca.CORPO)
    app.setFont(fonte)

    app.setStyleSheet(marca.folha_de_estilo())
    app.setWindowIcon(marca.icone_do_app())
