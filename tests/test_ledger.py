"""Livro-razão — ESCOPO.md §11 itens 1, 4 e 6. São os testes que impedem perda de dados."""
import pytest

from estoque_facil.core import kits, ledger
from estoque_facil.core.models import TipoMovimento


def test_invariante_soma_dos_movimentos_e_o_saldo(session, com_estoque):
    """O teste mais importante do projeto (§11.1)."""
    ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 2, referencia_externa="V1")
    ledger.aplicar_venda(session, com_estoque["mord.mao.rosa"], 1, referencia_externa="V2")
    ledger.aplicar_venda(session, com_estoque["kit.combo"], 1, referencia_externa="V3")
    ledger.entrada_compra(session, com_estoque["mord.pe.rosa"], 10)
    ledger.ajustar(session, com_estoque["manta.rosa"], 3)
    session.commit()

    assert ledger.verificar_invariante(session) == []


def test_venda_de_kit_baixa_os_componentes(session, com_estoque):
    ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 2, referencia_externa="V1")
    assert ledger.saldo_de(session, com_estoque["mord.mao.rosa"]) == 12
    assert ledger.saldo_de(session, com_estoque["mord.pe.rosa"]) == 4


def test_componente_compartilhado_soma_as_baixas(session, com_estoque):
    """O caso real dela: mord.mao.rosa sai por dois kits e avulso."""
    ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 2, referencia_externa="V1")
    ledger.aplicar_venda(session, com_estoque["mord.mao.rosa"], 1, referencia_externa="V2")
    ledger.aplicar_venda(session, com_estoque["kit.combo"], 1, referencia_externa="V3")
    assert ledger.saldo_de(session, com_estoque["mord.mao.rosa"]) == 14 - 2 - 1 - 1


def test_idempotencia_a_mesma_venda_nao_baixa_duas_vezes(session, com_estoque):
    """Venda de kit gera vários movimentos com a mesma referência — o caso que mais quebra."""
    r1 = ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 2, referencia_externa="V1")
    assert len(r1.movimentos) == 2 and r1.ignorados == 0

    r2 = ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 2, referencia_externa="V1")
    assert r2.movimentos == [] and r2.ignorados == 2

    assert ledger.saldo_de(session, com_estoque["mord.pe.rosa"]) == 4
    assert ledger.verificar_invariante(session) == []


def test_movimento_guarda_por_qual_kit_o_item_saiu(session, com_estoque):
    ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 1, referencia_externa="V9")
    movs = ledger.historico(session, com_estoque["mord.pe.rosa"])
    venda = [m for m in movs if m.tipo == TipoMovimento.VENDA][0]
    assert venda.produto_vendido.sku == "KIT.MAOPE.ROSA"
    assert "saiu por KIT.MAOPE.ROSA" in ledger.descrever(venda)


def test_devolucao_de_kit_volta_como_componentes(session, com_estoque):
    ledger.aplicar_venda(session, com_estoque["KIT.MAOPE.ROSA"], 1, referencia_externa="V1")
    ledger.aplicar_devolucao(session, com_estoque["KIT.MAOPE.ROSA"], 1, referencia_externa="V1")
    assert ledger.saldo_de(session, com_estoque["mord.mao.rosa"]) == 14
    assert ledger.saldo_de(session, com_estoque["mord.pe.rosa"]) == 6


def test_saldo_negativo_e_permitido_mas_visivel(session, com_estoque):
    """Travar a importação faria ela desistir do app (§5.1). Negativo é informação real."""
    ledger.aplicar_venda(session, com_estoque["mord.pe.rosa"], 10, referencia_externa="V1")
    assert ledger.saldo_de(session, com_estoque["mord.pe.rosa"]) == -4
    assert kits.disponivel(session, com_estoque["KIT.MAOPE.ROSA"]).quantidade == 0


def test_custo_medio_ponderado(session, catalogo):
    p = catalogo["mord.mao.rosa"]
    ledger.entrada_compra(session, p, 10, custo_unitario=10.0)
    assert p.custo == 10.0
    ledger.entrada_compra(session, p, 10, custo_unitario=20.0)
    assert p.custo == 15.0


def test_ajuste_leva_ao_valor_exato(session, com_estoque):
    ledger.ajustar(session, com_estoque["mord.mao.rosa"], 7)
    assert ledger.saldo_de(session, com_estoque["mord.mao.rosa"]) == 7
    assert ledger.ajustar(session, com_estoque["mord.mao.rosa"], 7) is None


def test_recalcular_saldos_reconstroi_o_cache(session, com_estoque):
    ledger.aplicar_venda(session, com_estoque["kit.combo"], 2, referencia_externa="V1")
    session.commit()

    # corrompe o cache de propósito
    from sqlalchemy import select

    from estoque_facil.core.models import Saldo

    saldo = session.scalars(select(Saldo)).first()
    saldo.quantidade = 999
    session.flush()
    assert ledger.verificar_invariante(session) != []

    ledger.recalcular_saldos(session)
    assert ledger.verificar_invariante(session) == []


def test_movimento_zero_e_recusado(session, com_estoque):
    with pytest.raises(ledger.ErroEstoque):
        ledger.registrar(session, com_estoque["mord.mao.rosa"], 0, TipoMovimento.AJUSTE)
