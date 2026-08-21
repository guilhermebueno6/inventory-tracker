import os
import tempfile
from pathlib import Path

import pytest

os.environ["ESTOQUE_FACIL_DIR"] = tempfile.mkdtemp(prefix="ef_test_")

from estoque_facil.core import db, kits, repo  # noqa: E402
from estoque_facil.core.models import TipoProduto  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session(tmp_path, monkeypatch):
    """Cada teste com sua pasta de dados própria.

    ESTOQUE_FACIL_DIR precisa apontar para a MESMA pasta do banco aberto: senão
    `db.caminho_banco()` devolve um caminho diferente do engine da sessão, e o
    código de backup/migração mexe num banco que não é o do teste.
    """
    monkeypatch.setenv("ESTOQUE_FACIL_DIR", str(tmp_path))
    db.iniciar()
    s = db.sessao()
    yield s
    s.close()


@pytest.fixture
def catalogo(session):
    """Cenário real dela: dois kits e um combo compartilhando componentes."""
    p = {}
    for sku, custo in [
        ("mord.mao.rosa", 6.75), ("mord.pe.rosa", 6.75),
        ("mord.mao.azul", 6.75), ("mord.pe.azul", 6.75),
        ("manta.rosa", 11.90), ("embalagem", 1.00),
    ]:
        p[sku] = repo.criar_produto(session, sku, sku, custo=custo)

    for sku, comps, custo in [
        ("KIT.MAOPE.ROSA", {"mord.mao.rosa": 1, "mord.pe.rosa": 1}, 13.50),
        ("KIT.MAOPE.AZUL", {"mord.mao.azul": 1, "mord.pe.azul": 1}, 13.50),
        ("kit.combo", {"mord.mao.rosa": 1, "mord.mao.azul": 1, "embalagem": 2}, 15.50),
    ]:
        kit = repo.criar_produto(session, sku, sku, tipo=TipoProduto.KIT, custo=custo)
        kits.definir_composicao(session, kit, {p[c].id: q for c, q in comps.items()})
        p[sku] = kit

    session.commit()
    return p


@pytest.fixture
def com_estoque(session, catalogo):
    from estoque_facil.core import ledger

    quantidades = {
        "mord.mao.rosa": 14, "mord.pe.rosa": 6,
        "mord.mao.azul": 10, "mord.pe.azul": 20,
        "manta.rosa": 5, "embalagem": 80,
    }
    for sku, qtd in quantidades.items():
        ledger.entrada_compra(session, catalogo[sku], qtd)
    session.commit()
    return catalogo
