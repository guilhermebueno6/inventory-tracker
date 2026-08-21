"""Evolução do banco entre versões — ESCOPO.md §10.1 passo 7.

Este módulo existe por causa de um risco concreto: `Base.metadata.create_all()`
cria tabelas que faltam, mas **não altera tabela que já existe**. Numa versão que
acrescentasse uma coluna, o app instalado quebraria com "no such column" e o
único conserto óbvio seria apagar o banco — perdendo o estoque inteiro.

Com Alembic, cada versão nova traz as instruções de como transformar o banco
antigo no novo, preservando os dados. E antes de qualquer migração o banco é
copiado, para que exista um caminho de volta.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

PASTA_MIGRACOES = Path(__file__).resolve().parent.parent / "migracoes"
REVISAO_BASE = "0001"


def _config(engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(PASTA_MIGRACOES))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return cfg


def revisao_do_banco(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def revisao_do_codigo() -> str | None:
    return ScriptDirectory.from_config(_config_vazio()).get_current_head()


def _config_vazio() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(PASTA_MIGRACOES))
    return cfg


def backup_antes_de_migrar(caminho_db: Path) -> Path | None:
    """Cópia do banco antes de mexer no schema. Barato, e é a rede de segurança."""
    caminho_db = Path(caminho_db)
    if not caminho_db.exists():
        return None
    destino = caminho_db.parent / "backups" / "antes-de-atualizar"
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    copia = destino / f"estoque-{carimbo}.db"
    from .db import copiar_banco

    copiar_banco(copia, caminho_db)
    log.info("banco copiado para %s antes da migração", copia)
    return copia


def garantir_atualizado(engine: Engine, caminho_db: Path | None = None) -> str:
    """Deixa o banco na revisão mais nova. Devolve o que foi feito.

    Três situações:
      • banco novo (sem tabelas)     → cria tudo e marca na revisão atual
      • banco de uma versão anterior → aplica as migrações (com backup antes)
      • banco já em dia              → não faz nada
    """
    inspetor = inspect(engine)
    tabelas = set(inspetor.get_table_names())
    cfg = _config(engine)
    alvo = revisao_do_codigo()

    if not tabelas:
        from .models import Base

        Base.metadata.create_all(engine)
        command.stamp(cfg, "head")
        log.info("banco novo criado na revisão %s", alvo)
        return "criado"

    atual = revisao_do_banco(engine)

    if atual is None:
        # Banco criado antes de existirem migrações (as primeiras instalações).
        # O schema equivale ao baseline, então basta carimbá-lo.
        command.stamp(cfg, REVISAO_BASE)
        atual = REVISAO_BASE
        log.info("banco sem controle de versão — marcado como %s", REVISAO_BASE)

    if atual == alvo:
        return "em dia"

    if caminho_db:
        backup_antes_de_migrar(Path(caminho_db))
    log.info("migrando o banco de %s para %s", atual, alvo)

    from .db import sem_chaves_estrangeiras

    with sem_chaves_estrangeiras(engine):
        command.upgrade(cfg, "head")
    return f"migrado de {atual} para {alvo}"
