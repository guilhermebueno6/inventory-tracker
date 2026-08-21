"""Importação ponta a ponta contra os ARQUIVOS REAIS dela — ESCOPO.md §11 itens 3, 4, 5, 6."""
from pathlib import Path

import pytest

from estoque_facil.core import kits, ledger, repo
from estoque_facil.core.models import CASA, TipoProduto
from estoque_facil.importers import ml_vendas_xlsx
from estoque_facil.services import importacao
from estoque_facil.services.importacao import Situacao

FIXTURES = Path(__file__).parent / "fixtures"
VENDAS = FIXTURES / "vendas_ml_exemplo.xlsx"
CATALOGO = FIXTURES / "atributosprodutos.csv"


# ----------------------------------------------------------------- parser do ML


def test_le_o_relatorio_real():
    r = ml_vendas_xlsx.ler(VENDAS)
    assert len(r.linhas) == 51
    assert r.periodo_inicio.date().isoformat() == "2026-08-12"
    assert r.periodo_fim.date().isoformat() == "2026-08-21"
    assert r.total_unidades == 57
    assert all(ln.data is not None for ln in r.linhas), "nenhuma data pode falhar no parse"
    assert all(ln.sku for ln in r.linhas), "SKU está 100% preenchido neste relatório"


def test_classifica_por_forma_de_entrega_nao_pelo_deposito():
    """§2.5 — o erro que a v1.0 do escopo cometeu."""
    r = ml_vendas_xlsx.ler(VENDAS)
    assert {ln.local for ln in r.linhas} == {CASA}
    assert {ln.deposito for ln in r.linhas} == {"Carapicuíba Alameda dos Babaçu"}
    assert ml_vendas_xlsx.classificar_local("Fulfillment") == "FULL"
    assert ml_vendas_xlsx.classificar_local("Correios e pontos de envio") == CASA


def test_arquivo_errado_da_mensagem_util(tmp_path):
    ruim = tmp_path / "qualquer.xlsx"
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = "outra coisa"
    wb.save(ruim)
    with pytest.raises(ml_vendas_xlsx.ErroArquivoML, match="Vendas → Exportar"):
        ml_vendas_xlsx.ler(ruim)


def test_datas_em_portugues():
    d = ml_vendas_xlsx.parse_data("21 de agosto de 2026 16:10 hs.")
    assert (d.day, d.month, d.year, d.hour) == (21, 8, 2026, 16)
    assert ml_vendas_xlsx.parse_data("5 de março de 2026").month == 3
    assert ml_vendas_xlsx.parse_data("lixo") is None


# ------------------------------------------------------------- carga do catálogo


def test_importa_os_195_skus_reais(session):
    r = importacao.importar_catalogo(session, CATALOGO)
    session.commit()
    assert r.criados == 195
    assert r.kits_marcados == 75
    assert repo.contar(session) == {"total": 195, "kits": 75, "simples": 120}

    p = repo.por_sku(session, "KIT.MAOPE.ROSA")
    assert p.custo == 13.50 and p.tipo == TipoProduto.KIT
    # casamento é case-insensitive (§2.4)
    assert repo.por_sku(session, "kit.maope.rosa").id == p.id


def test_reimportar_o_catalogo_nao_duplica(session):
    importacao.importar_catalogo(session, CATALOGO)
    session.commit()
    r = importacao.importar_catalogo(session, CATALOGO)
    session.commit()
    assert r.criados == 0 and r.atualizados == 195


def test_relatorio_preenche_os_nomes(session):
    importacao.importar_catalogo(session, CATALOGO)
    session.commit()
    assert not repo.por_sku(session, "KIT.MAOPE.ROSA").nome

    n = importacao.preencher_nomes(session, VENDAS)
    session.commit()
    assert n == 16, "o relatório de 8 dias cobre 16 dos 195 SKUs"
    p = repo.por_sku(session, "KIT.MAOPE.ROSA")
    assert "Mordedor" in p.nome and p.ml_item_id.startswith("MLB")


# ----------------------------------------------------- importação real de vendas


@pytest.fixture
def catalogo_real(session):
    importacao.importar_catalogo(session, CATALOGO)
    importacao.preencher_nomes(session, VENDAS)
    session.commit()
    return session


def test_analise_nao_grava_nada(catalogo_real, session):
    antes = len(ledger.historico(session, repo.por_sku(session, "mord.mao.azul")))
    importacao.analisar_vendas(session, VENDAS)
    assert len(ledger.historico(session, repo.por_sku(session, "mord.mao.azul"))) == antes


def test_kits_sem_composicao_ficam_pendentes_e_nao_travam_o_resto(catalogo_real, session):
    """O comportamento da §5.1: bloqueia a linha, nunca a importação inteira."""
    a = importacao.analisar_vendas(session, VENDAS)
    pendentes = a.por(Situacao.SEM_CADASTRO)
    assert pendentes, "os 9 SKUs de kit ainda não têm composição"
    assert all("composição" in p.motivo for p in pendentes)
    assert a.aplicaveis, "as vendas de itens simples passam normalmente"


def test_importacao_completa_com_composicoes(catalogo_real, session):
    # define a composição do kit mais vendido (25% das vendas)
    kit = repo.por_sku(session, "KIT.MAOPE.ROSA")
    kits.definir_composicao(
        session,
        kit,
        {
            repo.por_sku(session, "mord.mao.rosa").id: 1,
            repo.por_sku(session, "mord.pe.rosa").id: 1,
        },
    )
    for sku in ("mord.mao.rosa", "mord.pe.rosa"):
        ledger.entrada_compra(session, repo.por_sku(session, sku), 100)
    session.commit()

    a = importacao.analisar_vendas(session, VENDAS)
    resumo = importacao.confirmar_vendas(session, a)
    session.commit()

    # 13 unidades do KIT.MAOPE.ROSA vendidas → 13 de cada componente
    assert ledger.saldo_de(session, repo.por_sku(session, "mord.mao.rosa")) == 100 - 13
    assert ledger.saldo_de(session, repo.por_sku(session, "mord.pe.rosa")) == 100 - 13
    assert resumo.vendas_aplicadas > 0
    assert ledger.verificar_invariante(session) == []


def test_reimportar_o_mesmo_arquivo_nao_muda_nada(catalogo_real, session):
    """§2.3 — a garantia mais importante do app."""
    a1 = importacao.analisar_vendas(session, VENDAS)
    importacao.confirmar_vendas(session, a1)
    session.commit()
    saldos = {
        p.sku: ledger.saldo_de(session, p)
        for p in repo.buscar(session, tipo=TipoProduto.SIMPLES)
    }

    a2 = importacao.analisar_vendas(session, VENDAS)
    assert a2.aplicaveis == [], "tudo deve cair em 'já processada'"
    assert len(a2.por(Situacao.JA_PROCESSADA)) == len(a1.aplicaveis)

    importacao.confirmar_vendas(session, a2)
    session.commit()
    depois = {
        p.sku: ledger.saldo_de(session, p)
        for p in repo.buscar(session, tipo=TipoProduto.SIMPLES)
    }
    assert saldos == depois
    assert ledger.verificar_invariante(session) == []


def test_desfazer_lote_restaura_o_estado_anterior(catalogo_real, session):
    antes = {
        p.sku: ledger.saldo_de(session, p)
        for p in repo.buscar(session, tipo=TipoProduto.SIMPLES)
    }
    a = importacao.analisar_vendas(session, VENDAS)
    resumo = importacao.confirmar_vendas(session, a)
    session.commit()
    assert any(
        ledger.saldo_de(session, repo.por_sku(session, sku)) != antes[sku]
        for sku in antes
    )

    ledger.desfazer_lote(session, resumo.lote_id)
    session.commit()
    depois = {
        p.sku: ledger.saldo_de(session, p)
        for p in repo.buscar(session, tipo=TipoProduto.SIMPLES)
    }
    assert antes == depois
    assert ledger.verificar_invariante(session) == []


def test_pode_reimportar_depois_de_desfazer(catalogo_real, session):
    """Sem isso, desfazer viraria uma armadilha: o arquivo nunca mais entraria."""
    a = importacao.analisar_vendas(session, VENDAS)
    resumo = importacao.confirmar_vendas(session, a)
    session.commit()
    ledger.desfazer_lote(session, resumo.lote_id)
    session.commit()

    a2 = importacao.analisar_vendas(session, VENDAS)
    assert len(a2.aplicaveis) == len(a.aplicaveis)
