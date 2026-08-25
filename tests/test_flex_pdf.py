"""Etiquetas do Flex em PDF — ESCOPO.md §2.9.

Contra o arquivo REAL que o ML gera (só os nomes dos compradores foram trocados
por fictícios). O que estes testes protegem, em ordem de importância:

  1. Duas colunas: o nome do comprador não pode virar título de produto.
  2. O N.º de venda é o mesmo do Excel — importar os dois não baixa duas vezes.
  3. O PDF não tem valores: pode mexer no estoque, não pode mexer no balanço.
"""
from pathlib import Path

import pytest
from sqlalchemy import func, select

from estoque_facil.core import ledger, repo
from estoque_facil.core.models import CASA, VendaItem
from estoque_facil.importers import ml_flex_pdf
from estoque_facil.services import importacao
from estoque_facil.services.importacao import Situacao

FIXTURES = Path(__file__).parent / "fixtures"
ETIQUETAS = FIXTURES / "etiquetas_flex_exemplo.pdf"
VENDAS = FIXTURES / "vendas_ml_exemplo.xlsx"
CATALOGO = FIXTURES / "atributosprodutos.csv"


# ------------------------------------------------------------------- o parser


def test_le_as_16_etiquetas_reais():
    r = ml_flex_pdf.ler(ETIQUETAS)
    assert len(r.linhas) == 16
    assert r.tipo == "vendas_flex_pdf"
    assert r.avisos == []
    assert all(ln.numero_venda.isdigit() for ln in r.linhas)
    assert all(ln.sku for ln in r.linhas), "SKU é o que casa com o catálogo"
    assert r.total_unidades == 17, "15 etiquetas de 1 unidade + 1 de 2 unidades"


def test_separa_as_duas_colunas_do_pdf():
    """A armadilha nº 1: no texto corrido o comprador cai no meio do produto."""
    r = ml_flex_pdf.ler(ETIQUETAS)
    primeira = r.linhas[0]
    assert primeira.numero_venda == "2000018089398690"
    assert primeira.sku == "TROC.PORT.AZUL"
    assert primeira.quantidade == 2
    assert primeira.titulo == "Trocador De Fraldas Compacto Impermeável Bebê"
    assert primeira.variacao == "Cor : Azul | Nome do desenho : Ramos"
    # nenhum nome de comprador escapou para o lado dos produtos
    assert all("Ana Souza" not in ln.titulo for ln in r.linhas)


def test_etiqueta_e_sempre_estoque_de_casa():
    """Flex é despacho próprio: não sai do Full (§2.5)."""
    r = ml_flex_pdf.ler(ETIQUETAS)
    assert {ln.local for ln in r.linhas} == {CASA}
    assert all(ln.abate for ln in r.linhas)
    assert not any(ln.status_desconhecido for ln in r.linhas)


def test_data_vem_do_pdf_quando_o_nome_do_arquivo_nao_diz():
    """A etiqueta é impressa no dia do despacho — serve de data da venda."""
    r = ml_flex_pdf.ler(ETIQUETAS)
    assert r.periodo_inicio.date().isoformat() == "2026-08-24"
    assert r.periodo_inicio == r.periodo_fim
    assert all(ln.data == r.periodo_inicio for ln in r.linhas)


def test_nenhuma_linha_traz_dinheiro():
    r = ml_flex_pdf.ler(ETIQUETAS)
    assert not any(ln.tem_financeiro for ln in r.linhas)
    assert all(ln.total == 0.0 and ln.preco_unitario == 0.0 for ln in r.linhas)


def test_pdf_que_nao_e_etiqueta_da_mensagem_util(tmp_path):
    from pypdf import PdfWriter

    ruim = tmp_path / "outro.pdf"
    escritor = PdfWriter()
    escritor.add_blank_page(width=595, height=842)
    with open(ruim, "wb") as f:
        escritor.write(f)

    with pytest.raises(ml_flex_pdf.ErroArquivoFlex, match="Imprimir etiquetas"):
        ml_flex_pdf.ler(ruim)


def test_arquivo_ilegivel_nao_estoura_erro_tecnico(tmp_path):
    ruim = tmp_path / "quebrado.pdf"
    ruim.write_bytes(b"isto nao e um PDF")
    with pytest.raises(ml_flex_pdf.ErroArquivoFlex):
        ml_flex_pdf.ler(ruim)


def test_o_funil_escolhe_o_parser_pela_extensao():
    assert importacao.ler_relatorio(ETIQUETAS).tipo == "vendas_flex_pdf"
    assert importacao.ler_relatorio(VENDAS).tipo == "vendas_ml"


# --------------------------------------------------------- importação de fato


@pytest.fixture
def catalogo_real(session):
    importacao.importar_catalogo(session, CATALOGO)
    session.commit()
    return session


def test_baixa_o_estoque_das_vendas_flex(catalogo_real, session):
    """O motivo do módulo existir: essas vendas não estão no Excel."""
    vendido = repo.por_sku(session, "pompom.M28")
    ledger.entrada_compra(session, vendido, 50)
    session.commit()

    analise = importacao.analisar_vendas(session, ETIQUETAS)
    importacao.confirmar_vendas(session, analise)
    session.commit()

    assert ledger.saldo_de(session, vendido) == 50 - 2, "duas etiquetas deste SKU"
    assert ledger.verificar_invariante(session) == []


def test_nao_mexe_no_balanco(catalogo_real, session):
    """§2.9 — receita inventada é pior do que receita faltando."""
    analise = importacao.analisar_vendas(session, ETIQUETAS)
    assert analise.sem_valores
    resumo = importacao.confirmar_vendas(session, analise)
    session.commit()

    assert resumo.sem_valores
    assert resumo.linhas_financeiras == 0
    assert session.scalar(select(func.count()).select_from(VendaItem)) == 0


def test_reimportar_a_mesma_etiqueta_nao_baixa_de_novo(catalogo_real, session):
    a1 = importacao.analisar_vendas(session, ETIQUETAS)
    importacao.confirmar_vendas(session, a1)
    session.commit()
    saldos = {p.sku: ledger.saldo_de(session, p) for p in repo.buscar(session)}

    a2 = importacao.analisar_vendas(session, ETIQUETAS)
    assert a2.aplicaveis == []
    assert len(a2.por(Situacao.JA_PROCESSADA)) == len(a1.aplicaveis)

    importacao.confirmar_vendas(session, a2)
    session.commit()
    assert saldos == {p.sku: ledger.saldo_de(session, p) for p in repo.buscar(session)}


def test_venda_que_ja_veio_pela_planilha_nao_repete_no_pdf(catalogo_real, session):
    """A garantia que faz valer a pena poder importar os dois arquivos (§2.3).

    O N.º de venda é o mesmo nos dois formatos, e a deduplicação é por ele — não
    por arquivo. Aqui a venda entra como se tivesse vindo do Excel; o PDF tem de
    reconhecê-la.
    """
    linha = ml_flex_pdf.ler(ETIQUETAS).linhas[0]
    produto = repo.por_sku(session, linha.sku)
    ledger.entrada_compra(session, produto, 10)
    ledger.aplicar_venda(
        session, produto, linha.quantidade, referencia_externa=linha.numero_venda
    )
    session.commit()
    saldo = ledger.saldo_de(session, produto)

    analise = importacao.analisar_vendas(session, ETIQUETAS)
    repetida = [ln for ln in analise.linhas if ln.origem.numero_venda == linha.numero_venda]
    assert [ln.situacao for ln in repetida] == [Situacao.JA_PROCESSADA]

    # O MESMO SKU aparece em outra etiqueta, de uma venda que ainda não entrou:
    # essa tem que baixar. A garantia é por N.º de venda, não por produto.
    novas = sum(ln.origem.quantidade for ln in analise.aplicaveis if ln.produto is produto)
    assert novas == 1

    importacao.confirmar_vendas(session, analise)
    session.commit()
    assert ledger.saldo_de(session, produto) == saldo - novas


def test_lote_guarda_de_onde_veio(catalogo_real, session):
    from estoque_facil.core.models import LoteImportacao

    analise = importacao.analisar_vendas(session, ETIQUETAS)
    resumo = importacao.confirmar_vendas(session, analise)
    session.commit()

    lote = session.get(LoteImportacao, resumo.lote_id)
    assert lote.tipo == "vendas_flex_pdf"
    assert lote.arquivo_nome == ETIQUETAS.name


def test_desfazer_devolve_o_estoque_da_etiqueta(catalogo_real, session):
    antes = {p.sku: ledger.saldo_de(session, p) for p in repo.buscar(session)}
    analise = importacao.analisar_vendas(session, ETIQUETAS)
    resumo = importacao.confirmar_vendas(session, analise)
    session.commit()
    assert any(ledger.saldo_de(session, repo.por_sku(session, s)) != antes[s] for s in antes)

    ledger.desfazer_lote(session, resumo.lote_id)
    session.commit()
    assert antes == {p.sku: ledger.saldo_de(session, p) for p in repo.buscar(session)}
    assert ledger.verificar_invariante(session) == []


def test_etiqueta_tambem_preenche_nomes(catalogo_real, session):
    """O PDF traz o título do anúncio — serve para a carga inicial (§5.3)."""
    assert not repo.por_sku(session, "pompom.M28").nome
    n = importacao.preencher_nomes(session, ETIQUETAS)
    session.commit()
    assert n > 0
    assert "Pom Pom" in repo.por_sku(session, "pompom.M28").nome


# ------------------------------------------------- etiquetas fora do comum
#
# Coisas que o arquivo real não tem, mas a loja dela vai ter um dia. As
# etiquetas abaixo são escritas à mão, sem biblioteca de geração de PDF, porque
# o que precisa ficar à vista é justamente a GEOMETRIA: coluna da esquerda em
# x=31, coluna da direita em x=261, uma linha por Y.


def _pdf_de_etiqueta(caminho: Path, textos: list[tuple[float, float, str]]) -> Path:
    """PDF de uma página com cada texto na coordenada (x, y) pedida."""
    corpo = "\n".join(
        f"BT\n/F1 8 Tf\n{x:.4f} {y:.4f} Td\n({texto}) Tj\nET" for x, y, texto in textos
    ).encode("latin-1")

    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length %d>>\nstream\n%s\nendstream" % (len(corpo), corpo),
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]

    saida, deslocamentos = bytearray(b"%PDF-1.4\n"), []
    for i, obj in enumerate(objetos, start=1):
        deslocamentos.append(len(saida))
        saida += b"%d 0 obj\n%s\nendobj\n" % (i, obj)

    inicio = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for d in deslocamentos:
        saida += b"%010d 00000 n \n" % d
    saida += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1, inicio
    )
    caminho.write_bytes(bytes(saida))
    return caminho


def _etiqueta_boa(y: float, envio: str, venda: str) -> list[tuple[float, float, str]]:
    return [
        (31, y, envio), (31, y - 10, f"Venda: {venda}"), (31, y - 21, "Cliente Teste"),
        (261, y, "Mordedor Mao Rosa"), (261, y - 10, "SKU: mord.mao.rosa"),
        (261, y - 21, "Quantidade: 1"),
    ]


def test_uma_etiqueta_com_dois_produtos(tmp_path):
    """Os dois itens herdam o MESMO N.º de venda — e cada um a sua quantidade."""
    pdf = _pdf_de_etiqueta(tmp_path / "duplo.pdf", [
        (31, 723, "47800000001"), (31, 713, "Venda: 2000000000001"),
        (31, 702, "Cliente Teste"),
        (261, 723, "Kit Livros de Banho"), (261, 713, "SKU:"), (278, 713, "kit.livros"),
        (261, 702, "Quantidade: 1"),
        (261, 691, "Mordedor Mao Rosa"), (261, 680, "SKU: mord.mao.rosa"),
        (261, 669, "Quantidade: 3"), (261, 658, "Cor: Rosa"),
    ])
    linhas = ml_flex_pdf.ler(pdf).linhas
    assert [(ln.numero_venda, ln.sku, ln.quantidade) for ln in linhas] == [
        ("2000000000001", "kit.livros", 1),
        ("2000000000001", "mord.mao.rosa", 3),
    ]
    assert linhas[0].titulo == "Kit Livros de Banho"
    assert linhas[1].variacao == "Cor : Rosa"


def test_etiqueta_sem_quantidade_assume_uma_e_avisa(tmp_path):
    pdf = _pdf_de_etiqueta(tmp_path / "sem_qtd.pdf", [
        (31, 723, "47800000001"), (31, 713, "Venda: 2000000000001"),
        (261, 723, "Mordedor Mao Rosa"), (261, 713, "SKU: mord.mao.rosa"),
    ])
    linha = ml_flex_pdf.ler(pdf).linhas[0]
    assert linha.quantidade == 1
    assert "considerei 1 unidade" in linha.aviso


def test_a_linha_incerta_cai_na_aba_de_atencao(catalogo_real, session, tmp_path):
    """O aviso do parser tem que chegar na tela, não morrer no meio do caminho."""
    pdf = _pdf_de_etiqueta(tmp_path / "sem_qtd.pdf", [
        (31, 723, "47800000001"), (31, 713, "Venda: 2000000000001"),
        (261, 723, "Mordedor Mao Rosa"), (261, 713, "SKU: mord.mao.rosa"),
    ])
    analise = importacao.analisar_vendas(session, pdf)
    assert [ln.situacao for ln in analise.linhas] == [Situacao.ATENCAO]
    assert "considerei 1 unidade" in analise.linhas[0].motivo


def test_etiqueta_sem_numero_de_venda_fica_de_fora_com_aviso(tmp_path):
    """Sem a chave da §2.3 não dá para prometer que a baixa não repete."""
    pdf = _pdf_de_etiqueta(tmp_path / "sem_venda.pdf", [
        *_etiqueta_boa(723, "47800000001", "2000000000001"),
        (31, 660, "47800000002"), (31, 639, "Cliente Sem Venda"),
        (261, 660, "Mordedor Mao Azul"), (261, 650, "SKU: mord.mao.azul"),
        (261, 639, "Quantidade: 2"),
    ])
    r = ml_flex_pdf.ler(pdf)
    assert [ln.sku for ln in r.linhas] == ["mord.mao.rosa"]
    assert len(r.avisos) == 1 and "N.º de venda" in r.avisos[0]


def test_anuncio_sem_sku_fica_de_fora_com_aviso(tmp_path):
    """O PDF não traz o código MLB: sem SKU não há com o que casar (§2.4)."""
    pdf = _pdf_de_etiqueta(tmp_path / "sem_sku.pdf", [
        *_etiqueta_boa(723, "47800000001", "2000000000001"),
        (31, 660, "47800000002"), (31, 650, "Venda: 2000000000002"),
        (261, 660, "Anuncio Sem Sku"), (261, 650, "Quantidade: 1"),
    ])
    r = ml_flex_pdf.ler(pdf)
    assert [ln.sku for ln in r.linhas] == ["mord.mao.rosa"]
    assert len(r.avisos) == 1 and "não tem SKU" in r.avisos[0]


def test_pdf_so_de_etiquetas_ruins_explica_o_motivo(tmp_path):
    """Nada aproveitado não pode virar 'arquivo errado' — o motivo é outro."""
    pdf = _pdf_de_etiqueta(tmp_path / "so_ruins.pdf", [
        (31, 723, "47800000001"), (31, 702, "Cliente Sem Venda"),
        (261, 723, "Mordedor Mao Rosa"), (261, 713, "SKU: mord.mao.rosa"),
        (261, 702, "Quantidade: 1"),
    ])
    with pytest.raises(ml_flex_pdf.ErroArquivoFlex, match="N.º de venda"):
        ml_flex_pdf.ler(pdf)


def test_avisos_do_arquivo_chegam_na_tela(catalogo_real, session, tmp_path):
    pdf = _pdf_de_etiqueta(tmp_path / "misto.pdf", [
        *_etiqueta_boa(723, "47800000001", "2000000000001"),
        (31, 660, "47800000002"), (31, 639, "Cliente Sem Venda"),
        (261, 660, "Mordedor Mao Azul"), (261, 650, "SKU: mord.mao.azul"),
        (261, 639, "Quantidade: 2"),
    ])
    analise = importacao.analisar_vendas(session, pdf)
    assert analise.relatorio.avisos, "a tela mostra isto abaixo do resumo"
