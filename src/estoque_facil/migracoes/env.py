"""Ambiente do Alembic. Configurado por código — não existe alembic.ini no app."""
from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from estoque_facil.core.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexao = config.attributes.get("connection", None)
    if conexao is not None:
        _rodar(conexao)
        return
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as conn:
        _rodar(conn)


def _rodar(conexao) -> None:
    context.configure(
        connection=conexao,
        target_metadata=target_metadata,
        # SQLite não sabe ALTER TABLE de verdade: o batch mode recria a tabela,
        # copia os dados e troca. É o que permite evoluir o schema sem perder nada.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
