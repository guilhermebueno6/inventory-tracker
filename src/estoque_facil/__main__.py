"""Ponto de entrada do Estoque Fácil."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


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


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .core import db
    from .services import backup
    from .ui.main_window import JanelaPrincipal
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
    estilo = Path(__file__).parent / "ui" / "style.qss"
    if estilo.exists():
        app.setStyleSheet(estilo.read_text(encoding="utf-8"))

    janela = JanelaPrincipal(session)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
