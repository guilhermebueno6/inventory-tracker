"""Abre as telas de verdade (modo offscreen) com os dados reais — ESCOPO.md §11.9.

Não testa aparência: testa que a interface não quebra ao montar com dados de
verdade — 195 produtos, 75 kits, 51 vendas.
"""
import os
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from estoque_facil.core import kits, repo  # noqa: E402
from estoque_facil.services import importacao  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def sem_modais(monkeypatch):
    """Diálogos modais travam para sempre sem ninguém para clicar.

    Silenciá-los é o certo aqui: o teste verifica o ESTADO depois da ação
    (o item não entrou na composição), não o popup.
    """
    for modulo in ("estoque_facil.ui.tela_produto", "estoque_facil.ui.tela_importacao",
                   "estoque_facil.ui.main_window", "estoque_facil.ui.dialogos",
                   "estoque_facil.ui.tela_balanco"):
        for func in ("avisar", "informar"):
            monkeypatch.setattr(f"{modulo}.{func}", lambda *a, **k: None, raising=False)
        monkeypatch.setattr(f"{modulo}.confirmar", lambda *a, **k: True, raising=False)


@pytest.fixture
def loja(session):
    importacao.importar_catalogo(session, FIXTURES / "atributosprodutos.csv")
    importacao.preencher_nomes(session, FIXTURES / "vendas_ml_exemplo.xlsx")
    kit = repo.por_sku(session, "KIT.MAOPE.ROSA")
    kits.definir_composicao(
        session, kit,
        {repo.por_sku(session, "mord.mao.rosa").id: 1,
         repo.por_sku(session, "mord.pe.rosa").id: 1},
    )
    session.commit()
    return session


def test_janela_principal_abre(app, loja, session):
    from estoque_facil.ui.main_window import JanelaPrincipal

    j = JanelaPrincipal(session)
    assert j.windowTitle()
    j.inicial.recarregar()
    j.abrir_estoque()
    assert j.estoque.tabela.rowCount() == 195
    j.abrir_kits()
    # 75 kits, 1 já configurado
    assert j.kits_pendentes.tabela.rowCount() == 74
    j.voltar_inicio()


def test_lista_mostra_kit_como_da_para_montar(app, loja, session):
    from estoque_facil.ui.tela_estoque import TelaEstoque

    tela = TelaEstoque(session)
    tela.busca.setText("KIT.MAOPE.ROSA")
    tela.recarregar()
    assert tela.tabela.rowCount() >= 1
    linha = 0
    assert tela.tabela.item(linha, 2).text() == "Kit"
    assert "Dá para montar" in tela.tabela.item(linha, 3).text()


def test_editor_de_composicao_sugere_e_confere_custo(app, loja, session):
    from estoque_facil.ui.tela_produto import EditorComposicao

    kit = repo.por_sku(session, "KIT.MAOPE.AZUL")
    editor = EditorComposicao(session, kit)
    # nada configurado ainda, mas as sugestões precisam aparecer
    assert editor.lay_sugestoes.count() > 1
    editor._adicionar(repo.por_sku(session, "mord.mao.azul").id)
    editor._adicionar(repo.por_sku(session, "mord.pe.azul").id)
    assert len(editor.itens()) == 2
    # 6.75 + 6.75 = 13.50, exatamente o custo do kit
    assert "bate com o custo" in editor.lb_custo.text()


def test_editor_recusa_kit_dentro_de_kit(app, loja, session):
    from estoque_facil.ui.tela_produto import EditorComposicao

    kit = repo.por_sku(session, "KIT.MAOPE.AZUL")
    outro = repo.por_sku(session, "KIT.MAOPE.ROSA")
    editor = EditorComposicao(session, kit)
    editor._adicionar(outro.id)          # deve ser recusado silenciosamente na UI
    assert outro.id not in editor.itens()


# ------------------------------------------------------------------ exclusão
#
# `sem_modais` faz `confirmar` devolver True, então estes testes exercitam o
# caminho de quem clicou em "Excluir de vez" / "Arquivar".


def _selecionar(tela, texto):
    tela.busca.setText(texto)
    tela.recarregar()
    assert tela.tabela.rowCount() >= 1, f"nada encontrado para {texto}"
    tela.tabela.setCurrentCell(0, 0)
    return tela


def test_excluir_pela_lista_tira_o_produto_do_catalogo(app, loja, session):
    from estoque_facil.ui.tela_estoque import TelaEstoque

    repo.criar_produto(session, "zz.descartavel", "Item que ela não vende mais")
    session.commit()

    tela = _selecionar(TelaEstoque(session), "zz.descartavel")
    tela.excluir_selecionado()

    assert repo.por_sku(session, "zz.descartavel") is None
    assert tela.tabela.rowCount() == 0


def test_excluir_componente_de_kit_e_recusado_na_tela(app, loja, session):
    """A tela não pode ser um caminho mais frouxo que o núcleo — §5.2.5."""
    from estoque_facil.ui.tela_estoque import TelaEstoque

    tela = _selecionar(TelaEstoque(session), "mord.mao.rosa")
    tela.excluir_selecionado()

    assert repo.por_sku(session, "mord.mao.rosa") is not None


def test_produto_com_historico_e_arquivado_e_volta_pelo_filtro(app, loja, session):
    from estoque_facil.core import ledger
    from estoque_facil.ui.tela_estoque import TelaEstoque

    alvo = repo.criar_produto(session, "zz.usado", "Item com histórico")
    ledger.entrada_compra(session, alvo, 7)
    session.commit()

    tela = _selecionar(TelaEstoque(session), "zz.usado")
    tela.excluir_selecionado()

    assert alvo.ativo is False
    assert tela.tabela.rowCount() == 0, "arquivado sai da lista normal"

    tela.filtro.setCurrentText("Arquivados")
    _selecionar(tela, "zz.usado")
    assert "Arquivado" in tela.tabela.item(0, 4).text()

    tela.reativar_selecionado()
    assert alvo.ativo is True
    assert ledger.saldo_de(session, alvo) == 7


def test_arquivado_com_historico_nao_pode_ser_apagado_de_vez(app, loja, session):
    from estoque_facil.core import exclusao, ledger
    from estoque_facil.ui.tela_estoque import TelaEstoque

    alvo = repo.criar_produto(session, "zz.usado", "Item com histórico")
    ledger.entrada_compra(session, alvo, 3)
    exclusao.arquivar(session, alvo)
    session.commit()

    tela = TelaEstoque(session)
    tela.filtro.setCurrentText("Arquivados")
    _selecionar(tela, "zz.usado")
    tela.excluir_selecionado()

    assert repo.por_sku(session, "zz.usado") is not None


def test_kits_pendentes_pode_excluir_o_kit_que_ela_nao_vende_mais(app, loja, session):
    from estoque_facil.ui.tela_kits import TelaKitsPendentes

    tela = TelaKitsPendentes(session)
    antes = tela.tabela.rowCount()
    sku = tela.tabela.item(0, 0).text()
    tela.tabela.setCurrentCell(0, 0)

    tela.excluir()

    assert repo.por_sku(session, sku) is None
    assert tela.tabela.rowCount() == antes - 1


def test_tela_do_produto_so_oferece_excluir_ao_editar(app, loja, session):
    from estoque_facil.ui.tela_produto import TelaProduto

    assert not hasattr(TelaProduto(session, None), "bt_excluir")
    assert hasattr(TelaProduto(session, repo.por_sku(session, "mord.mao.rosa")),
                   "bt_excluir")


def test_tela_de_importacao_classifica_as_linhas(app, loja, session, monkeypatch):
    from estoque_facil.services.importacao import Situacao
    from estoque_facil.ui.tela_importacao import TelaImportacao

    tela = TelaImportacao(session, FIXTURES / "vendas_ml_exemplo.xlsx")
    a = tela.analise
    assert a is not None
    assert len(a.relatorio.linhas) == 51
    assert a.aplicaveis, "vendas de itens simples e do kit configurado devem passar"
    assert a.por(Situacao.SEM_CADASTRO), "os kits sem composição ficam pendentes"
    assert tela.abas.count() >= 2
    assert tela.bt_confirmar.isEnabled()
    assert "venda" in a.resumo().lower()


# ------------------------------------------------------------------- balanço


def test_tela_de_balanco_mostra_a_conta_fechada(app, loja, session):
    """A tela precisa abrir com dados de verdade e fechar a conta na última linha."""
    from estoque_facil.services import financeiro, importacao
    from estoque_facil.ui.tela_balanco import TelaBalanco

    analise = importacao.analisar_vendas(session, FIXTURES / "vendas_ml_exemplo.xlsx")
    importacao.confirmar_vendas(session, analise)
    financeiro.registrar_despesa(
        session, "Caixas de papelão", 200, data=datetime(2026, 8, 3)
    )
    session.commit()

    tela = TelaBalanco(session)
    # o relatório é de agosto de 2026; a tela abre no mês corrente
    tela.periodo.setCurrentIndex(tela.periodo.count() - 1)   # "Escolher as datas…"
    tela.f_inicio.setDate(QDate(2026, 8, 1))
    tela.f_fim.setDate(QDate(2026, 8, 31))
    tela.recarregar()

    assert tela.balanco is not None
    assert tela.balanco.vendas == 51
    assert tela.tabela.rowCount() == len(tela.balanco.linhas())
    assert tela.tabela.item(tela.tabela.rowCount() - 1, 0).text().startswith("= Lucro")
    assert tela.tabela_produtos.rowCount() > 0
    assert "R$" in tela.tabela.item(0, 1).text()
    assert "Caixas" not in tela.lb_despesas.text()      # a linha mostra a categoria
    assert "R$ 200,00" in tela.lb_despesas.text()


def test_dialogo_de_despesa_lanca_e_o_balanco_ve(app, loja, session):
    from estoque_facil.services import financeiro
    from estoque_facil.ui.dialogos import DialogoDespesa

    d = DialogoDespesa(session)
    d.descricao.setText("Anúncio patrocinado")
    d.valor.setValue(75.5)
    d._salvar()

    hoje = datetime.now()
    b = financeiro.apurar(session, *financeiro.mes(hoje.year, hoje.month))
    assert b.despesas == 75.5
    assert b.lucro == -75.5


def test_dialogo_de_despesa_recusa_sem_descricao(app, loja, session):
    from estoque_facil.services import financeiro
    from estoque_facil.ui.dialogos import DialogoDespesa

    d = DialogoDespesa(session)
    d.valor.setValue(30)
    d._salvar()                     # sem descrição: o aviso está silenciado no teste
    assert financeiro.listar_despesas(session) == []


def test_dialogo_de_ajuste_registra_perda(app, loja, session):
    from estoque_facil.core import ledger, repo
    from estoque_facil.ui.dialogos import DialogoAjuste

    produto = repo.por_sku(session, "mord.mao.rosa")
    ledger.entrada_compra(session, produto, 10)
    session.commit()

    d = DialogoAjuste(session, produto)
    assert d.combo.currentData() == produto.id, "abre já no produto selecionado"
    d.motivo.setCurrentIndex(0)                     # "Quebrou ou estragou"
    d.qtd.setValue(3)
    d.descricao.setText("caixa molhada")
    assert "perda de R$" in d.lb_efeito.text()
    d._salvar()

    assert ledger.saldo_de(session, produto) == 7


# --------------------------------------------------------------------- layout
#
# Testes de regressão do layout. O primeiro relato de bug foi exatamente isto:
# o diálogo do kit passou da tela e o botão Salvar ficou inalcançável.


def _largura_util(tabela):
    return tabela.viewport().width()


def test_botao_salvar_fica_dentro_da_janela_mesmo_com_kit_grande(app, loja, session):
    """Se o Salvar sair da tela, a tela inteira fica inutilizável."""
    from estoque_facil.ui.tela_produto import TelaProduto

    kit = repo.por_sku(session, "KIT.ENXMAT.ROSA")
    d = TelaProduto(session, kit)
    d.chk_kit.setChecked(True)
    d._montar_editor()
    d._sincronizar_visibilidade()
    d.resize(880, 780)
    d.show()
    for sku in ("mord.mao.rosa", "mord.pe.rosa", "manta.rosa", "cueiro.rosa",
                "babador.rosa", "livro.animaisdomar"):
        p = repo.por_sku(session, sku)
        if p:
            d.editor._adicionar(p.id)
    app.processEvents()

    fundo = d.bt_salvar.mapTo(d, d.bt_salvar.rect().bottomLeft()).y()
    assert fundo <= d.height(), "o botão Salvar saiu da janela"
    assert d.bt_salvar.isVisible()


def test_dialogo_nao_fica_maior_que_a_tela(app, loja, session):
    from PySide6.QtGui import QGuiApplication

    from estoque_facil.ui.tela_produto import TelaProduto

    tela = QGuiApplication.primaryScreen().availableGeometry()
    # o nome deste produto é longo o bastante para ter estourado a largura antes
    kit = repo.por_sku(session, "KIT.MAOPE.ROSA")
    assert len(kit.nome) > 50, "fixture precisa de um nome longo para o teste valer"
    d = TelaProduto(session, kit)
    d.show()
    app.processEvents()
    assert d.width() <= tela.width()
    assert d.height() <= tela.height()


def test_colunas_cabem_na_largura_da_tabela(app, loja, session):
    """Nenhuma coluna pode ser empurrada para fora da tabela."""
    from estoque_facil.ui.tela_balanco import TelaBalanco
    from estoque_facil.ui.tela_estoque import TelaEstoque
    from estoque_facil.ui.tela_kits import TelaKitsPendentes

    for tela in (TelaEstoque(session), TelaKitsPendentes(session), TelaBalanco(session)):
        tela.resize(1080, 720)
        tela.show()
        app.processEvents()
        t = tela.tabela
        soma = sum(t.columnWidth(i) for i in range(t.columnCount()))
        assert soma <= _largura_util(t) + 2, (
            f"{type(tela).__name__}: colunas somam {soma}px "
            f"para {_largura_util(t)}px de tabela"
        )


def test_celulas_longas_guardam_o_texto_inteiro_no_tooltip(app, loja, session):
    """Coluna estreita corta o texto — o tooltip garante que nada suma."""
    from estoque_facil.ui.tela_estoque import TelaEstoque

    tela = TelaEstoque(session)
    tela.busca.setText("KIT.AZULCUEIROSBABETEPANOBOCAFAIXA")
    tela.recarregar()
    assert tela.tabela.rowCount() == 1
    assert tela.tabela.item(0, 0).toolTip() == "KIT.AZULCUEIROSBABETEPANOBOCAFAIXA"
