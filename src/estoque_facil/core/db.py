"""Conexão, criação do banco e caminhos por sistema operacional — ESCOPO.md §3.1.

Os dados NUNCA ficam ao lado do executável: em Windows, Program Files é somente leitura.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from platformdirs import user_data_dir
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..version import APP_DIR
from .models import CASA, FULL, LocalEstoque

_engine: Engine | None = None
_Session: sessionmaker | None = None


def pasta_dados() -> Path:
    """`%LOCALAPPDATA%\\EstoqueFacil` no Windows, `~/Library/Application Support/...` no Mac.

    `ESTOQUE_FACIL_DIR` sobrescreve — usado pelos testes e por instalação em pendrive.
    """
    override = os.environ.get("ESTOQUE_FACIL_DIR")
    base = Path(override) if override else Path(user_data_dir(APP_DIR, appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    for sub in ("backups", "importados", "fotos", "logs"):
        (base / sub).mkdir(exist_ok=True)
    return base


def caminho_banco() -> Path:
    return pasta_dados() / "estoque.db"


# Durante uma migração as chaves estrangeiras precisam ficar desligadas.
# Motivo: o SQLite não sabe ALTER TABLE de verdade, então o Alembic recria a
# tabela (cria nova, copia, dropa, renomeia). Com foreign_keys=ON, o DROP da
# tabela antiga esbarra nas referências de `saldo` e `movimento` e a migração
# falha no meio. É por conexão, e por isso o pool é descartado ao ligar/desligar.
_migrando = False


@event.listens_for(Engine, "connect")
def _pragmas(dbapi_connection, _record):
    """WAL protege contra corrupção em queda de energia; foreign_keys o SQLite não liga sozinho."""
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=OFF" if _migrando else "PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


@contextmanager
def sem_chaves_estrangeiras(engine: Engine) -> Iterator[None]:
    """Desliga as FKs no pool inteiro enquanto o bloco roda."""
    global _migrando
    _migrando = True
    engine.dispose()          # força conexões novas, já sem FK
    try:
        yield
    finally:
        _migrando = False
        engine.dispose()      # e de volta ao normal


def iniciar(caminho: Path | str | None = None, echo: bool = False) -> Engine:
    global _engine, _Session
    destino = Path(caminho) if caminho else caminho_banco()
    _engine = create_engine(f"sqlite:///{destino}", echo=echo, future=True)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)

    # NUNCA usar create_all sozinho aqui: ele cria tabelas que faltam, mas não
    # altera as que já existem. Numa versão que acrescente uma coluna, o banco
    # dela quebraria. Ver core/migracoes.py.
    from .migracoes import garantir_atualizado

    resultado = garantir_atualizado(_engine, destino)
    logging.getLogger(__name__).info("banco: %s", resultado)

    with _Session() as s:
        _garantir_locais(s)
        s.commit()
    return _engine


def _garantir_locais(session: Session) -> None:
    """CASA é o que ela vê. FULL existe mas fica em segundo plano (ESCOPO.md §2.5)."""
    padroes = [
        (CASA, "Estoque de casa", "proprio", True),
        (FULL, "Mercado Envios Full", "marketplace", False),
    ]
    for codigo, nome, tipo, visivel in padroes:
        existe = session.scalar(select(LocalEstoque).where(LocalEstoque.codigo == codigo))
        if not existe:
            session.add(LocalEstoque(codigo=codigo, nome=nome, tipo=tipo, visivel=visivel))


def sessao() -> Session:
    if _Session is None:
        iniciar()
    assert _Session is not None
    return _Session()


@contextmanager
def transacao() -> Iterator[Session]:
    """Tudo ou nada. A importação inteira usa isto (ESCOPO.md §5.1 passo 7)."""
    s = sessao()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def local_id(session: Session, codigo: str = CASA) -> int:
    local = session.scalar(select(LocalEstoque).where(LocalEstoque.codigo == codigo))
    if local is None:
        _garantir_locais(session)
        session.flush()
        local = session.scalar(select(LocalEstoque).where(LocalEstoque.codigo == codigo))
    assert local is not None
    return local.id


def copiar_banco(destino: Path | str, origem: Path | str | None = None) -> Path:
    """Cópia CONSISTENTE do banco — usar sempre isto, nunca `shutil.copy`.

    Em modo WAL as escritas recentes ficam no arquivo `.db-wal`, e o `.db` pode
    estar praticamente vazio. Copiar só o `.db` produz um backup inútil — foi
    exatamente o que aconteceu aqui: 4 KB no `.db` contra 424 KB no `-wal`.

    A API de backup do SQLite lê o banco lógico inteiro (WAL incluído), funciona
    com o banco aberto em uso e entrega um arquivo já consolidado.
    """
    origem = Path(origem) if origem else caminho_banco()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fonte = sqlite3.connect(str(origem))
    alvo = sqlite3.connect(str(destino))
    try:
        fonte.backup(alvo)
    finally:
        alvo.close()
        fonte.close()
    return destino
