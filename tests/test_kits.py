"""Kits — ESCOPO.md §4.2, §5.2 e §11 itens 2, 3 e 7."""
import pytest

from estoque_facil.core import kits, ledger, repo
from estoque_facil.core.kits import ErroComposicao
from estoque_facil.core.models import TipoProduto


def test_disponibilidade_e_o_gargalo(session, com_estoque):
    d = kits.disponivel(session, com_estoque["KIT.MAOPE.ROSA"])
    assert d.quantidade == 6, "min(14//1, 6//1) = 6"
    assert d.gargalo.sku == "mord.pe.rosa"


def test_quantidade_maior_que_um_por_componente(session, com_estoque):
    # kit.combo usa 2 embalagens: min(14, 10, 80//2) = 10
    assert kits.disponivel(session, com_estoque["kit.combo"]).quantidade == 10


def test_componente_zerado_zera_todos_os_kits_que_dependem_dele(session, com_estoque):
    ledger.ajustar(session, com_estoque["mord.mao.rosa"], 0)
    assert kits.disponivel(session, com_estoque["KIT.MAOPE.ROSA"]).quantidade == 0
    assert kits.disponivel(session, com_estoque["kit.combo"]).quantidade == 0
    assert kits.disponivel(session, com_estoque["KIT.MAOPE.AZUL"]).quantidade == 10


def test_kit_nao_tem_estoque_proprio(session, com_estoque):
    with pytest.raises(ledger.ErroEstoque, match="não tem estoque próprio"):
        ledger.entrada_compra(session, com_estoque["KIT.MAOPE.ROSA"], 5)


def test_explosao_multiplica_pela_quantidade_vendida(session, com_estoque):
    itens = kits.explodir(session, com_estoque["kit.combo"], 3)
    por_sku = {i.produto.sku: i.quantidade for i in itens}
    assert por_sku == {"mord.mao.rosa": 3, "mord.mao.azul": 3, "embalagem": 6}
    assert all(i.vendido_como.sku == "kit.combo" for i in itens)


def test_produto_simples_explode_em_si_mesmo(session, com_estoque):
    itens = kits.explodir(session, com_estoque["mord.mao.rosa"], 4)
    assert len(itens) == 1
    assert itens[0].quantidade == 4 and itens[0].vendido_como is None


def test_cascata_lista_todos_os_kits_afetados(session, com_estoque):
    afetados = {k.sku for k in kits.kits_afetados(session, com_estoque["mord.mao.rosa"])}
    assert afetados == {"KIT.MAOPE.ROSA", "kit.combo"}
    assert kits.kits_afetados(session, com_estoque["manta.rosa"]) == []


def test_kit_dentro_de_kit_e_recusado(session, com_estoque):
    alvo = com_estoque["KIT.MAOPE.ROSA"]
    with pytest.raises(ErroComposicao, match="Kit dentro de kit"):
        kits.definir_composicao(
            session, alvo, {com_estoque["KIT.MAOPE.AZUL"].id: 1}
        )


def test_composicao_vazia_e_recusada(session, com_estoque):
    with pytest.raises(ErroComposicao, match="pelo menos um item"):
        kits.definir_composicao(session, com_estoque["KIT.MAOPE.ROSA"], {})


def test_kit_nao_pode_conter_ele_mesmo(session, com_estoque):
    alvo = com_estoque["KIT.MAOPE.ROSA"]
    with pytest.raises(ErroComposicao):
        kits.definir_composicao(session, alvo, {alvo.id: 1})


def test_kit_sem_composicao_bloqueia_a_venda_com_mensagem_util(session):
    kit = repo.criar_produto(session, "KIT.NOVO", "Kit novo", tipo=TipoProduto.KIT)
    with pytest.raises(ErroComposicao, match="ainda não tem composição"):
        kits.explodir(session, kit, 1)


def test_nao_vira_kit_se_ja_e_componente_de_outro(session, com_estoque):
    pode, motivo = kits.pode_virar_kit(session, com_estoque["mord.mao.rosa"])
    assert pode is False
    assert "KIT.MAOPE.ROSA" in motivo or "kit.combo" in motivo


def test_vira_kit_quando_esta_livre(session, com_estoque):
    pode, _ = kits.pode_virar_kit(session, com_estoque["manta.rosa"])
    assert pode is True


def test_custo_confere_a_composicao(session, com_estoque):
    ok, soma, _, _ = kits.conferir_custo(session, com_estoque["KIT.MAOPE.ROSA"])
    assert ok and soma == 13.50

    # tira um componente: o custo passa a acusar
    kits.definir_composicao(
        session, com_estoque["KIT.MAOPE.ROSA"], {com_estoque["mord.mao.rosa"].id: 1}
    )
    ok, soma, dif, msg = kits.conferir_custo(session, com_estoque["KIT.MAOPE.ROSA"])
    assert not ok and soma == 6.75 and "Faltam" in msg


def test_kits_sem_composicao_alimenta_a_tela_de_pendencias(session, com_estoque):
    repo.criar_produto(session, "KIT.VAZIO", "Vazio", tipo=TipoProduto.KIT)
    session.flush()
    pendentes = {k.sku for k in kits.kits_sem_composicao(session)}
    assert pendentes == {"KIT.VAZIO"}
