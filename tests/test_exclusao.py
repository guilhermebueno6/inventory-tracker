"""Excluir e arquivar produtos — ESCOPO.md §5.2.6.

O que estes testes protegem, em uma frase: **nenhum caminho de exclusão pode
apagar movimento**. Se um dia alguém "simplificar" o módulo apagando o
histórico junto, o invariante do §4.1 cai e o teste de saldo denuncia.
"""
import pytest
from sqlalchemy import select

from estoque_facil.core import exclusao, kits, ledger, repo
from estoque_facil.core.exclusao import ErroExclusao
from estoque_facil.core.models import Composicao, Movimento, Produto, TipoProduto

# ------------------------------------------------------------------ excluir

def test_produto_sem_historico_e_apagado_de_vez(session, catalogo):
    novo = repo.criar_produto(session, "avulso", "Item avulso")
    session.commit()

    assert exclusao.analisar(session, novo).pode_excluir is True
    exclusao.excluir(session, novo)
    session.commit()

    assert repo.por_sku(session, "avulso") is None


def test_excluir_kit_leva_a_composicao_mas_nao_os_itens(session, catalogo):
    kit = catalogo["KIT.MAOPE.AZUL"]
    kit_id = kit.id
    assert exclusao.analisar(session, kit).componentes == 2

    exclusao.excluir(session, kit)
    session.commit()

    assert repo.por_sku(session, "KIT.MAOPE.AZUL") is None
    assert session.scalars(
        select(Composicao).where(Composicao.kit_id == kit_id)
    ).all() == []
    # os mordedores continuam no catálogo, intactos
    assert repo.por_sku(session, "mord.mao.azul") is not None
    assert repo.por_sku(session, "mord.pe.azul") is not None


def test_excluir_apaga_o_vinculo_aprendido_do_ml(session, catalogo):
    novo = repo.criar_produto(session, "avulso", "Item avulso")
    repo.criar_vinculo(session, "MLB123", novo)
    session.commit()

    exclusao.excluir(session, novo)
    session.commit()

    assert repo.por_vinculo(session, "MLB123") is None


# ------------------------------------------------ histórico bloqueia o apagar

def test_item_com_movimento_nao_e_apagado(session, com_estoque):
    manta = com_estoque["manta.rosa"]
    analise = exclusao.analisar(session, manta)
    assert analise.movimentos == 1 and analise.pode_excluir is False

    with pytest.raises(ErroExclusao, match="Arquive-o"):
        exclusao.excluir(session, manta)


def test_kit_vendido_nao_e_apagado_mesmo_sem_estoque_proprio(session, com_estoque):
    """O kit não tem saldo, mas os movimentos dos componentes apontam para ele."""
    kit = com_estoque["KIT.MAOPE.ROSA"]
    ledger.aplicar_venda(session, kit, 1, referencia_externa="2000000001")
    session.commit()

    analise = exclusao.analisar(session, kit)
    assert analise.movimentos == 2, "um movimento por componente, ambos citam o kit"
    assert analise.pode_excluir is False


def test_arquivar_preserva_o_historico_e_o_saldo(session, com_estoque):
    manta = com_estoque["manta.rosa"]
    antes = ledger.saldo_de(session, manta)

    exclusao.arquivar(session, manta)
    session.commit()

    assert manta.ativo is False
    assert ledger.saldo_de(session, manta) == antes
    assert session.scalars(
        select(Movimento).where(Movimento.produto_id == manta.id)
    ).all() != []
    assert ledger.verificar_invariante(session) == []


def test_arquivado_some_das_listas_e_dos_contadores(session, com_estoque):
    antes = repo.contar(session)["total"]
    exclusao.arquivar(session, com_estoque["manta.rosa"])
    session.commit()

    assert repo.contar(session)["total"] == antes - 1
    assert "manta.rosa" not in {p.sku for p in repo.buscar(session, "manta")}
    assert "manta.rosa" in {p.sku for p in exclusao.arquivados(session)}


def test_reativar_traz_de_volta_com_o_estoque_que_tinha(session, com_estoque):
    manta = com_estoque["manta.rosa"]
    exclusao.arquivar(session, manta)
    session.commit()
    exclusao.reativar(session, manta)
    session.commit()

    assert manta.ativo is True
    assert repo.buscar(session, "manta.rosa")[0].id == manta.id
    assert ledger.saldo_de(session, manta) == 5


# ------------------------------------------------------- kits que dependem dele

def test_componente_usado_em_kit_e_recusado_com_os_nomes(session, com_estoque):
    analise = exclusao.analisar(session, com_estoque["mord.mao.rosa"])
    assert analise.bloqueado is True
    assert "KIT.MAOPE.ROSA" in analise.motivo_bloqueio
    assert "kit.combo" in analise.motivo_bloqueio


def test_componente_usado_em_kit_nao_pode_nem_ser_arquivado(session, com_estoque):
    """Arquivar deixaria o kit apontando para um item invisível — §5.2.5."""
    with pytest.raises(ErroExclusao, match="faz parte de"):
        exclusao.arquivar(session, com_estoque["mord.mao.rosa"])
    with pytest.raises(ErroExclusao, match="faz parte de"):
        exclusao.excluir(session, com_estoque["mord.mao.rosa"])


def test_kit_arquivado_aparece_marcado_no_motivo(session, com_estoque):
    """Senão a mensagem manda procurar um kit que sumiu das listas."""
    exclusao.arquivar(session, com_estoque["KIT.MAOPE.ROSA"])
    exclusao.arquivar(session, com_estoque["kit.combo"])
    session.commit()

    motivo = exclusao.analisar(session, com_estoque["mord.mao.rosa"]).motivo_bloqueio
    assert "(arquivado)" in motivo


def test_sai_da_composicao_e_ai_pode_ser_excluido(session, catalogo):
    """O caminho que a mensagem de bloqueio manda seguir precisa funcionar."""
    alvo = catalogo["mord.pe.azul"]
    kits.definir_composicao(
        session, catalogo["KIT.MAOPE.AZUL"], {catalogo["mord.mao.azul"].id: 1}
    )
    session.commit()

    exclusao.excluir(session, alvo)
    session.commit()
    assert repo.por_sku(session, "mord.pe.azul") is None


# ------------------------------------------------------------------ invariante

def test_exclusao_nunca_mexe_no_livro_razao(session, com_estoque):
    total_antes = session.scalars(select(Movimento)).all()
    novo = repo.criar_produto(session, "descartavel", "Descartável")
    session.commit()

    exclusao.excluir(session, novo)
    exclusao.arquivar(session, com_estoque["manta.rosa"])
    session.commit()

    assert len(session.scalars(select(Movimento)).all()) == len(total_antes)
    assert ledger.verificar_invariante(session) == []


def test_produto_arquivado_nao_entra_em_kit_novo(session, com_estoque):
    """`validar_componente` já recusava inativo; aqui garantimos o caminho inteiro."""
    exclusao.arquivar(session, com_estoque["manta.rosa"])
    session.commit()

    kit = repo.criar_produto(session, "KIT.NOVO", "Kit novo", tipo=TipoProduto.KIT)
    with pytest.raises(kits.ErroComposicao, match="inativo"):
        kits.definir_composicao(session, kit, {com_estoque["manta.rosa"].id: 1})


def test_kit_arquivado_sai_da_lista_de_pendencias(session, catalogo):
    vazio = repo.criar_produto(session, "KIT.VAZIO", "Vazio", tipo=TipoProduto.KIT)
    session.commit()
    assert vazio in kits.kits_sem_composicao(session)

    exclusao.arquivar(session, vazio)
    session.commit()
    assert vazio not in kits.kits_sem_composicao(session)


def test_saldo_do_produto_excluido_some_junto(session, catalogo):
    from estoque_facil.core.models import Saldo

    novo = repo.criar_produto(session, "avulso", "Item avulso")
    ledger.entrada_compra(session, novo, 3)
    session.commit()

    # com entrada ele tem histórico: só arquiva
    with pytest.raises(ErroExclusao):
        exclusao.excluir(session, novo)

    # sem histórico, o saldo zerado que sobrou não deixa lixo para trás
    outro = repo.criar_produto(session, "avulso2", "Outro")
    ledger._saldo_row(session, outro.id, 1)
    session.commit()
    outro_id = outro.id
    exclusao.excluir(session, outro)
    session.commit()
    assert session.scalars(
        select(Saldo).where(Saldo.produto_id == outro_id)
    ).all() == []


def test_produto_apagado_nao_deixa_orfao_no_banco(session, catalogo):
    novo = repo.criar_produto(session, "avulso", "Item avulso")
    session.commit()
    pid = novo.id

    exclusao.excluir(session, novo)
    session.commit()

    assert session.get(Produto, pid) is None


def test_venda_cancelada_conta_como_historico(session, catalogo):
    """Regressão: `venda_item` também aponta para `produto`.

    Uma venda CANCELADA grava a linha de dinheiro e nenhum movimento de estoque
    (`abateu_estoque=False`). Contando só `movimento`, o produto passava por
    `pode_excluir` e o DELETE morria na chave estrangeira — IntegrityError na
    cara da usuária, sem explicação e sem saída.
    """
    from estoque_facil.core.models import VendaItem

    alvo = repo.criar_produto(session, "so.cancelada", "Só vendeu e cancelou")
    session.add(
        VendaItem(numero_venda="9001", sku_ref="so.cancelada", produto_id=alvo.id,
                  cancelada=True, abateu_estoque=False, total_liquido=0.0)
    )
    session.commit()

    analise = exclusao.analisar(session, alvo)
    assert analise.movimentos == 0, "cancelada não mexe no estoque"
    assert analise.vendas == 1 and analise.registros == 1
    assert analise.pode_excluir is False

    with pytest.raises(ErroExclusao, match="histórico"):
        exclusao.excluir(session, alvo)

    # o caminho que sobra precisa funcionar
    exclusao.arquivar(session, alvo)
    session.commit()
    assert alvo.ativo is False


def test_produto_vendido_de_verdade_conta_as_duas_historias(session, com_estoque):
    """Movimento e venda_item contam juntos, sem dupla contagem virar mentira."""
    from estoque_facil.core.models import VendaItem

    alvo = com_estoque["manta.rosa"]
    session.add(
        VendaItem(numero_venda="9002", sku_ref="manta.rosa", produto_id=alvo.id)
    )
    session.commit()

    analise = exclusao.analisar(session, alvo)
    assert (analise.movimentos, analise.vendas) == (1, 1)
    assert "2 registros" in analise.resumo
