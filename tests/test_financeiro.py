"""Balanço da loja: vendas com valor, despesas e perdas — ESCOPO.md §4.4, §5.8 e §11.

O invariante desta parte é o irmão do invariante do estoque:

    estoque = soma dos movimentos          (test_ledger.py)
    lucro   = recebido − custo − imposto − perda − despesa   (aqui)

Nada de balanço é guardado como saldo: tudo é recalculado, sempre.
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from estoque_facil.core import kits, ledger, repo
from estoque_facil.core.models import (
    CategoriaDespesa,
    Despesa,
    TipoMovimento,
    VendaItem,
)
from estoque_facil.services import financeiro, importacao

FIXTURES = Path(__file__).parent / "fixtures"
VENDAS = FIXTURES / "vendas_ml_exemplo.xlsx"
CATALOGO = FIXTURES / "atributosprodutos.csv"

# O relatório real vai de 12 a 21 de agosto de 2026.
PERIODO = (datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59))


@pytest.fixture
def loja(session):
    """O cenário real: catálogo dela, um kit configurado e as 51 vendas."""
    importacao.importar_catalogo(session, CATALOGO)
    importacao.preencher_nomes(session, VENDAS)
    kit = repo.por_sku(session, "KIT.MAOPE.ROSA")
    kits.definir_composicao(
        session, kit,
        {repo.por_sku(session, "mord.mao.rosa").id: 1,
         repo.por_sku(session, "mord.pe.rosa").id: 1},
    )
    session.commit()
    return session


def _importar(session):
    analise = importacao.analisar_vendas(session, VENDAS)
    resumo = importacao.confirmar_vendas(session, analise)
    session.commit()
    return resumo


# ------------------------------------------------------------------- despesas


def test_despesa_exige_descricao_e_valor(session):
    with pytest.raises(financeiro.ErroFinanceiro, match="o que foi"):
        financeiro.registrar_despesa(session, "   ", 50)
    with pytest.raises(financeiro.ErroFinanceiro, match="maior que zero"):
        financeiro.registrar_despesa(session, "Caixas", 0)


def test_despesa_guarda_descricao_categoria_e_data(session):
    d = financeiro.registrar_despesa(
        session, "  Caixas de papelão  ", 128.5,
        data=datetime(2026, 8, 10), categoria=CategoriaDespesa.EMBALAGEM,
        observacao="nota 4471",
    )
    session.commit()
    assert d.descricao == "Caixas de papelão"
    assert d.valor == 128.5
    assert d.categoria_rotulo == "Embalagem e envio"
    assert d.observacao == "nota 4471"
    assert financeiro.listar_despesas(session, *PERIODO) == [d]
    # fora do período não aparece
    assert financeiro.listar_despesas(session, datetime(2026, 9, 1),
                                      datetime(2026, 9, 30)) == []


def test_despesa_apagada_sai_do_balanco(session):
    d = financeiro.registrar_despesa(session, "Anúncio", 90, data=datetime(2026, 8, 5))
    session.commit()
    assert financeiro.apurar(session, *PERIODO).despesas == 90
    financeiro.remover_despesa(session, d.id)
    session.commit()
    assert financeiro.apurar(session, *PERIODO).despesas == 0
    assert session.get(Despesa, d.id) is None


# --------------------------------------------------------- ajuste manual/perda


def test_perda_sai_do_estoque_e_custa_no_balanco(session, com_estoque):
    produto = com_estoque["mord.mao.rosa"]          # custo 6,75, estoque 14
    mov = ledger.ajuste_manual(session, produto, "quebra", 2, descricao="caiu da bancada")
    session.commit()

    assert mov.tipo == TipoMovimento.PERDA
    assert mov.quantidade == -2
    assert ledger.saldo_de(session, produto) == 12
    assert "Quebrou ou estragou: caiu da bancada" == mov.observacao

    inicio = datetime.now() - timedelta(days=1)
    fim = datetime.now() + timedelta(days=1)
    assert financeiro.apurar(session, inicio, fim).perdas == 13.5    # 2 × 6,75


def test_contagem_leva_para_o_numero_exato(session, com_estoque):
    produto = com_estoque["mord.pe.rosa"]           # 6 em estoque
    mov = ledger.ajuste_manual(session, produto, "contagem", 4, descricao="conferi na caixa")
    session.commit()
    assert mov.tipo == TipoMovimento.INVENTARIO
    assert mov.quantidade == -2
    assert ledger.saldo_de(session, produto) == 4
    # contagem não é perda: não custa nada no balanço
    assert financeiro.apurar(session, datetime(2020, 1, 1), datetime(2099, 1, 1)).perdas == 0


def test_contagem_que_bate_nao_cria_movimento(session, com_estoque):
    produto = com_estoque["mord.pe.rosa"]
    assert ledger.ajuste_manual(session, produto, "contagem", 6) is None


def test_sobra_encontrada_entra_no_estoque(session, com_estoque):
    produto = com_estoque["manta.rosa"]             # 5
    mov = ledger.ajuste_manual(session, produto, "sobra", 3)
    session.commit()
    assert mov.quantidade == 3
    assert ledger.saldo_de(session, produto) == 8


def test_ajuste_recusa_motivo_desconhecido_e_quantidade_negativa(session, com_estoque):
    produto = com_estoque["manta.rosa"]
    with pytest.raises(ledger.ErroEstoque, match="Motivo"):
        ledger.ajuste_manual(session, produto, "sei_la", 1)
    with pytest.raises(ledger.ErroEstoque, match="negativa"):
        ledger.ajuste_manual(session, produto, "quebra", -1)
    with pytest.raises(ledger.ErroEstoque, match="quantas"):
        ledger.ajuste_manual(session, produto, "quebra", 0)


def test_perda_de_componente_aparece_no_estoque_do_kit(session, com_estoque):
    kit = com_estoque["KIT.MAOPE.ROSA"]
    antes = kits.disponivel(session, kit).quantidade
    ledger.ajuste_manual(session, com_estoque["mord.pe.rosa"], "perda", 3)
    session.commit()
    assert kits.disponivel(session, kit).quantidade == antes - 3


# ------------------------------------------------------- vendas com valor (§5.8)


def test_importacao_guarda_o_dinheiro_de_toda_linha(loja, session):
    resumo = _importar(session)
    itens = session.query(VendaItem).all()

    # TODA linha do relatório vira uma linha financeira, inclusive as que não
    # baixaram estoque: a receita delas existe.
    assert len(itens) == 51
    assert resumo.linhas_financeiras == 51
    assert {i.lote_id for i in itens} == {resumo.lote_id}

    # e os números batem com o relatório lido direto do arquivo
    from estoque_facil.importers import ml_vendas_xlsx

    relatorio = ml_vendas_xlsx.ler(VENDAS)
    assert round(sum(i.total_liquido for i in itens), 2) == round(
        sum(ln.total for ln in relatorio.linhas), 2
    )
    assert round(sum(i.receita_produtos for i in itens), 2) == 2651.55
    assert round(sum(i.tarifa_venda for i in itens), 2) == -369.96


def test_as_partes_somam_o_total_do_mercado_livre(loja, session):
    """Se isto quebrar, o parser pegou a coluna errada — o erro mais provável (§2.2)."""
    _importar(session)
    for item in session.query(VendaItem).all():
        soma = (item.receita_produtos + item.receita_envio + item.tarifa_venda
                + item.tarifa_envio + item.descontos + item.cancelamentos)
        assert abs(round(soma - item.total_liquido, 2)) <= 0.02, item.numero_venda


def test_reimportar_o_mesmo_arquivo_nao_duplica_o_balanco(loja, session):
    """Idempotência do dinheiro — o irmão do teste de idempotência do estoque."""
    _importar(session)
    antes = financeiro.apurar(session, *PERIODO)

    _importar(session)
    depois = financeiro.apurar(session, *PERIODO)

    assert session.query(VendaItem).count() == 51
    assert depois.recebido == antes.recebido
    assert depois.cmv == antes.cmv
    assert depois.lucro == antes.lucro


def test_custo_do_kit_vendido_e_a_soma_dos_componentes(loja, session):
    _importar(session)
    kit = repo.por_sku(session, "KIT.MAOPE.ROSA")
    item = session.query(VendaItem).filter(VendaItem.produto_id == kit.id).first()
    assert item is not None
    esperado = kits.custo_montado(session, kit)
    assert esperado > 0
    assert item.custo_unitario == esperado
    assert item.custo_total == round(esperado * item.quantidade_faturada, 2)


def test_custo_gravado_e_uma_fotografia_do_momento_da_venda(loja, session):
    """Mudar o custo hoje não pode reescrever o lucro de ontem."""
    _importar(session)
    item = session.query(VendaItem).filter(VendaItem.custo_unitario > 0).first()
    custo_original = item.custo_unitario

    item.produto.custo = custo_original * 10
    session.commit()
    _importar(session)                       # reimporta o mesmo relatório

    session.refresh(item)
    assert item.custo_unitario == custo_original


def test_venda_sem_produto_cadastrado_entra_na_receita_e_avisa(session):
    """Receita existe mesmo sem custo — escondê-la daria um lucro que não existe.

    Cenário: relatório importado antes do catálogo. Nenhuma linha casa com
    produto, então nada baixa estoque — mas o dinheiro entrou de verdade.
    """
    _importar(session)

    itens = session.query(VendaItem).all()
    assert len(itens) == 51
    assert all(i.produto_id is None for i in itens)

    b = financeiro.apurar(session, *PERIODO)
    assert b.recebido > 0
    assert b.cmv == 0
    assert b.linhas_sem_custo == 51, "a tela precisa avisar que o lucro está inflado"


def test_kit_sem_composicao_usa_o_custo_do_catalogo(loja, session):
    """Melhor um custo aproximado do que lucro inflado por custo zero."""
    _importar(session)
    kit = repo.por_sku(session, "KIT.ENXMAT.ROSA")
    assert not kits.componentes_de(session, kit), "este kit ainda não foi configurado"
    item = session.query(VendaItem).filter(VendaItem.produto_id == kit.id).first()
    if item is not None:
        assert item.custo_unitario == pytest.approx(kit.custo)


def test_desfazer_importacao_leva_o_balanco_junto(loja, session):
    resumo = _importar(session)
    assert financeiro.apurar(session, *PERIODO).recebido != 0

    ledger.desfazer_lote(session, resumo.lote_id)
    session.commit()

    assert session.query(VendaItem).count() == 0
    balanco = financeiro.apurar(session, *PERIODO)
    assert balanco.recebido == 0
    assert balanco.vendas == 0


# ------------------------------------------------------------------- o balanço


def test_o_lucro_e_a_conta_inteira(loja, session):
    _importar(session)
    financeiro.registrar_despesa(
        session, "Caixas", 200, data=datetime(2026, 8, 3),
        categoria=CategoriaDespesa.EMBALAGEM,
    )
    financeiro.registrar_despesa(
        session, "Anúncio patrocinado", 150.5, data=datetime(2026, 8, 4),
        categoria=CategoriaDespesa.ANUNCIOS,
    )
    session.commit()

    b = financeiro.apurar(session, *PERIODO)

    assert b.vendas > 0
    assert b.despesas == 350.5
    assert b.despesas_por_categoria == {"Embalagem e envio": 200.0,
                                        "Anúncios e publicidade": 150.5}
    assert b.lucro == round(
        b.recebido - b.cmv - b.impostos - b.perdas - b.despesas, 2
    )
    # o recebido é a soma das linhas, e o subtotal da tela é o mesmo número
    rotulos = dict((r, v) for r, v, _t in b.linhas())
    assert rotulos["= Recebido do Mercado Livre"] == b.recebido
    assert rotulos["= Lucro do período"] == b.lucro
    assert rotulos["Despesas da loja"] == -350.5


def test_periodo_recorta_o_que_entra_na_conta(loja, session):
    _importar(session)
    cheio = financeiro.apurar(session, *PERIODO)
    assert cheio.vendas > 0

    # o relatório vai até 21/08; um período depois disso está vazio
    vazio = financeiro.apurar(session, datetime(2026, 9, 1), datetime(2026, 9, 30))
    assert vazio.vendas == 0
    assert vazio.recebido == 0
    assert not vazio.tem_dados

    # e um recorte no meio traz menos que o total
    meio = financeiro.apurar(session, datetime(2026, 8, 12),
                             datetime(2026, 8, 15, 23, 59, 59))
    assert 0 < meio.vendas < cheio.vendas
    assert meio.recebido < cheio.recebido


def test_por_produto_ordena_pelo_lucro(loja, session):
    _importar(session)
    linhas = financeiro.por_produto(session, *PERIODO)
    assert linhas
    assert [ln.lucro for ln in linhas] == sorted(
        (ln.lucro for ln in linhas), reverse=True
    )
    assert sum(ln.receita for ln in linhas) == pytest.approx(
        financeiro.apurar(session, *PERIODO).recebido, abs=0.05
    )


def test_perda_e_despesa_derrubam_o_lucro_do_mesmo_jeito(session, com_estoque):
    hoje = datetime.now()
    inicio, fim = financeiro.mes(hoje.year, hoje.month)

    ledger.ajuste_manual(session, com_estoque["manta.rosa"], "quebra", 2)  # 2 × 11,90
    financeiro.registrar_despesa(session, "Fita adesiva", 23.8, data=hoje)
    session.commit()

    b = financeiro.apurar(session, inicio, fim)
    assert b.perdas == 23.8
    assert b.despesas == 23.8
    assert b.lucro == -47.6


def test_exporta_a_planilha_do_periodo(loja, session, tmp_path):
    _importar(session)
    financeiro.registrar_despesa(session, "Caixas", 200, data=datetime(2026, 8, 3))
    session.commit()

    b = financeiro.apurar(session, *PERIODO)
    destino = financeiro.exportar_csv(session, b, tmp_path / "balanco.csv")

    texto = destino.read_text(encoding="utf-8-sig")
    assert "Balanço do período" in texto
    assert "= Lucro do período" in texto
    assert "Caixas" in texto


def test_cada_bloco_da_planilha_tem_cabecalho_do_tamanho_das_linhas(loja, session, tmp_path):
    """Cabeçalho curto joga o valor para uma coluna sem título — ela abre no
    Excel e vê 'Valor (R$)' em cima da categoria da despesa."""
    _importar(session)
    financeiro.registrar_despesa(session, "Caixas", 200, data=datetime(2026, 8, 3))
    session.commit()

    b = financeiro.apurar(session, *PERIODO)
    destino = financeiro.exportar_csv(session, b, tmp_path / "balanco.csv")

    with open(destino, newline="", encoding="utf-8-sig") as fh:
        linhas = list(csv.reader(fh, delimiter=";"))

    blocos: list[list[list[str]]] = [[]]
    for linha in linhas:
        if not linha:
            blocos.append([])
        else:
            blocos[-1].append(linha)
    blocos = [bloco for bloco in blocos if len(bloco) > 1]
    # Um bloco pode abrir com o título dele sozinho na primeira célula.
    blocos = [bloco[1:] if len(bloco[0]) == 1 else bloco for bloco in blocos]

    despesas = next(bl for bl in blocos if bl[0][0] == "Data")
    assert despesas[0] == ["Data", "Categoria", "Descrição", "Valor (R$)"]
    for bloco in blocos:
        cabecalho, *corpo = bloco
        for linha in corpo:
            assert len(linha) == len(cabecalho), f"{linha} não cabe em {cabecalho}"


def test_o_backup_leva_o_dinheiro_junto(loja, session, tmp_path):
    """Backup sem o financeiro perderia o balanço inteiro no primeiro susto."""
    from estoque_facil.services import backup

    _importar(session)
    financeiro.registrar_despesa(session, "Caixas", 200, data=datetime(2026, 8, 3))
    session.commit()

    pasta = backup.gerar(session, tmp_path, incluir_db=False)
    assert (pasta / "venda_item.csv").exists()
    assert "Caixas" in (pasta / "despesa.csv").read_text(encoding="utf-8-sig")


# ------------------------------------------------------------------- períodos


def test_atalhos_de_periodo_sao_intervalos_validos():
    hoje = datetime(2026, 8, 24, 15, 0)
    opcoes = financeiro.periodos(hoje)
    rotulos = [r for r, _i, _f in opcoes]
    assert "Este mês (agosto)" in rotulos[0]
    assert "julho" in rotulos[1]
    for _rotulo, inicio, fim in opcoes:
        assert inicio <= fim

    inicio, fim = financeiro.mes(2026, 2)
    assert (inicio.day, fim.day) == (1, 28)
