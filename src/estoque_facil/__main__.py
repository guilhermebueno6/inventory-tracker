"""Ponto de entrada do Estoque Fácil."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler


def _configurar_log():
    from .core.db import pasta_dados

    arquivo = pasta_dados() / "logs" / "app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(arquivo, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _verificar() -> int:
    """`--verificar`: abre o banco, aplica migrações e sai. Sem interface.

    É o teste de fumaça do build (pega dependência faltando no pacote, que só
    apareceria na máquina dela) e um diagnóstico rápido quando algo dá errado.
    """
    from .core import db, repo
    from .core.migracoes import revisao_do_banco
    from .ui import marca
    from .version import APP_NAME, __version__

    _configurar_log()
    engine = db.iniciar()
    with db.sessao() as s:
        contagem = repo.contar(s)
    print(f"{APP_NAME} {__version__}")
    print(f"  pasta de dados: {db.pasta_dados()}")
    print(f"  revisão do banco: {revisao_do_banco(engine)}")
    print(f"  produtos: {contagem['total']} ({contagem['kits']} kits)")

    # Carregar o Qt aqui é o que dá valor ao teste de fumaça: a falha mais
    # provável de empacotamento é a interface não achar seus plugins, e isso
    # não apareceria só abrindo o banco.
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from .ui.main_window import JanelaPrincipal
    from .ui.tema import vestir

    vestir(app)
    print(f"  fonte da marca: {marca.familia()}")

    # sem checar atualização: o teste de fumaça não deve depender de rede
    janela = JanelaPrincipal(db.sessao(), verificar_atualizacao=False)
    print(f"  interface: {janela.windowTitle()} carregou")
    janela.close()
    app.quit()
    print("  tudo certo")
    return 0


def main() -> int:
    if "--verificar" in sys.argv:
        return _verificar()

    from PySide6.QtWidgets import QApplication

    from .core import db
    from .services import backup
    from .ui.main_window import JanelaPrincipal
    from .ui.tema import vestir
    from .version import APP_NAME

    _configurar_log()
    log = logging.getLogger(__name__)
    log.info("iniciando %s", APP_NAME)

    db.iniciar()
    session = db.sessao()

    # Backup ao abrir — barato e já salvou muita gente (§7.1)
    try:
        backup.gerar(session, incluir_db=False)
    except Exception:  # noqa: BLE001
        log.exception("falha no backup de abertura")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    vestir(app)

    janela = JanelaPrincipal(session)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
