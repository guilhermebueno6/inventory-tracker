"""Atualizar o app não pode custar o estoque — ESCOPO.md §10.2 e §11.8.

Estes testes existem por causa de dois problemas reais encontrados:

1. `Base.metadata.create_all()` cria tabelas que faltam mas NÃO altera as que já
   existem. Uma versão nova com uma coluna a mais quebraria o banco instalado.
2. Em modo WAL, copiar só o arquivo `.db` produz um backup vazio — as escritas
   recentes estão no `.db-wal`. O `.db` tinha 4 KB contra 424 KB do WAL.
"""
import sqlite3
from pathlib import Path

from alembic import command

from estoque_facil.core import db, ledger, migracoes, repo
from estoque_facil.services import backup


def _dados_de_exemplo(session):
    p = repo.criar_produto(session, "mord.mao.rosa", "Mordedor rosa", custo=6.75)
    ledger.entrada_compra(session, p, 42)
    session.commit()
    return p


def test_backup_inclui_o_que_ainda_esta_no_wal(session, tmp_path):
    """O bug que tornava o backup inútil justamente quando ele era mais preciso."""
    _dados_de_exemplo(session)

    caminho = db.caminho_banco()
    tamanho_db = caminho.stat().st_size
    wal = caminho.with_name(caminho.name + "-wal")
    assert wal.exists() and wal.stat().st_size > tamanho_db, (
        "o cenário do teste depende de haver dados no WAL"
    )

    copia = db.copiar_banco(tmp_path / "copia.db")
    con = sqlite3.connect(copia)
    try:
        assert con.execute("SELECT COUNT(*) FROM produto").fetchone()[0] == 1
        assert con.execute("SELECT quantidade FROM saldo").fetchone()[0] == 42
    finally:
        con.close()


def test_backup_completo_carrega_o_banco_de_verdade(session, tmp_path):
    _dados_de_exemplo(session)
    pasta = backup.gerar(session, tmp_path, incluir_db=True)

    con = sqlite3.connect(pasta / "estoque.db")
    try:
        assert con.execute("SELECT COUNT(*) FROM produto").fetchone()[0] == 1
    finally:
        con.close()

    # a composição é o dado que mais custa a montar: precisa estar no CSV
    assert (pasta / "composicao.csv").exists()
    assert (pasta / "estoque.csv").exists()


def test_banco_de_versao_anterior_migra_preservando_os_dados(session, tmp_path):
    """Simula a atualização: banco na revisão antiga, código na revisão nova."""
    produto = _dados_de_exemplo(session)
    engine = session.get_bind()
    cfg = migracoes._config(engine)

    # volta o banco para a revisão anterior, como se fosse a versão instalada
    with db.sem_chaves_estrangeiras(engine):
        command.downgrade(cfg, "0001")
    assert migracoes.revisao_do_banco(engine) == "0001"
    con = sqlite3.connect(db.caminho_banco())
    try:
        colunas = {linha[1] for linha in con.execute("PRAGMA table_info(produto)")}
        assert "fornecedor" not in colunas, "o downgrade precisa ter tirado a coluna"
    finally:
        con.close()

    resultado = migracoes.garantir_atualizado(engine, db.caminho_banco())

    assert "migrado" in resultado
    assert migracoes.revisao_do_banco(engine) == migracoes.revisao_do_codigo()
    session.expire_all()
    assert repo.por_sku(session, "mord.mao.rosa") is not None
    assert ledger.saldo_de(session, repo.por_sku(session, "mord.mao.rosa")) == 42
    assert ledger.verificar_invariante(session) == []
    assert produto.sku == "mord.mao.rosa"


def test_migracao_faz_backup_antes(session, tmp_path):
    _dados_de_exemplo(session)
    engine = session.get_bind()
    with db.sem_chaves_estrangeiras(engine):
        command.downgrade(migracoes._config(engine), "0001")

    pasta = db.caminho_banco().parent / "backups" / "antes-de-atualizar"
    antes = len(list(pasta.glob("*.db"))) if pasta.exists() else 0

    migracoes.garantir_atualizado(engine, db.caminho_banco())

    copias = sorted(pasta.glob("*.db"))
    assert len(copias) == antes + 1, "toda migração precisa deixar uma cópia de segurança"
    con = sqlite3.connect(copias[-1])
    try:
        assert con.execute("SELECT COUNT(*) FROM produto").fetchone()[0] == 1
    finally:
        con.close()


def test_banco_sem_controle_de_versao_e_adotado(session):
    """Instalações feitas antes das migrações existirem não podem quebrar."""
    engine = session.get_bind()
    _dados_de_exemplo(session)
    with engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("DROP TABLE alembic_version"))

    assert migracoes.revisao_do_banco(engine) is None
    migracoes.garantir_atualizado(engine, db.caminho_banco())
    assert migracoes.revisao_do_banco(engine) == migracoes.revisao_do_codigo()
    assert repo.contar(session)["total"] == 1


def test_banco_novo_ja_nasce_na_revisao_atual(tmp_path):
    engine = db.iniciar(tmp_path / "novo.db")
    assert migracoes.revisao_do_banco(engine) == migracoes.revisao_do_codigo()
    assert migracoes.garantir_atualizado(engine, tmp_path / "novo.db") == "em dia"


def test_os_dados_ficam_fora_da_pasta_do_programa():
    """Desinstalar o app não pode levar o estoque junto."""
    import sys

    pasta = db.pasta_dados()
    programa = str(Path(sys.argv[0]).resolve().parent) if sys.argv[0] else ""
    assert programa not in str(pasta) or not programa
