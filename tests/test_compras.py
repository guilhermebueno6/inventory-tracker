"""Lista de compras — o mínimo do item somado ao que os kits reservam.

O caso que a lista existe para resolver está em
`test_minimo_do_kit_soma_com_o_minimo_do_item`: com mínimo 10 no item e mínimo
10 num kit que usa 1 unidade dele, 15 em estoque já é pouco — e nenhum alerta
que olhe só o mínimo do item percebe isso.
"""
from estoque_facil.core import exclusao, ledger
from estoque_facil.services import compras


def _por_sku(linhas):
    return {n.produto.sku: n for n in linhas}


def test_item_no_limite_do_proprio_minimo_entra(session, com_estoque):
    """"Igual ou abaixo": no limite exato a lista já avisa."""
    item = com_estoque["manta.rosa"]        # 5 em estoque
    item.estoque_minimo = 5
    session.commit()

    linha = _por_sku(compras.lista_de_compras(session))["manta.rosa"]
    assert linha.precisa_ter == 5
    assert linha.faltam == 0                # está no limite, não abaixo dele


def test_item_acima_do_minimo_fica_de_fora(session, com_estoque):
    item = com_estoque["manta.rosa"]        # 5 em estoque
    item.estoque_minimo = 4
    session.commit()

    assert "manta.rosa" not in _por_sku(compras.lista_de_compras(session))


def test_item_sem_minimo_nenhum_fica_de_fora(session, com_estoque):
    """Sem mínimo definido não há o que comparar — e zero não é alerta."""
    assert compras.lista_de_compras(session) == []


def test_minimo_do_kit_soma_com_o_minimo_do_item(session, com_estoque):
    """O exemplo do escopo: item 10 + kit 10 (1 por kit) e 15 em estoque → entra."""
    item = com_estoque["mord.mao.rosa"]
    ledger.entrada_compra(session, item, 1)             # 14 + 1 = 15
    item.estoque_minimo = 10
    com_estoque["KIT.MAOPE.ROSA"].estoque_minimo = 10
    session.commit()

    linha = _por_sku(compras.lista_de_compras(session))["mord.mao.rosa"]
    assert linha.saldo == 15
    assert linha.minimo_proprio == 10
    assert linha.reservado_para_kits == 10
    assert linha.precisa_ter == 20
    assert linha.faltam == 5
    assert "KIT.MAOPE.ROSA" in linha.porque


def test_dois_kits_somam_a_reserva_do_mesmo_item(session, com_estoque):
    """`mord.mao.rosa` está em dois kits — é onde a conta na mão desiste.

    Nenhum dos dois mínimos sozinho passa das 14 unidades em estoque; a SOMA
    passa. Quem olhasse um kit de cada vez concluiria que está tudo bem.
    """
    com_estoque["KIT.MAOPE.ROSA"].estoque_minimo = 8     # 1 por kit  →  8
    com_estoque["kit.combo"].estoque_minimo = 7          # 1 por kit  →  7
    session.commit()

    linha = _por_sku(compras.lista_de_compras(session))["mord.mao.rosa"]
    assert linha.saldo == 14
    assert linha.reservado_para_kits == 15
    assert linha.precisa_ter == 15                        # o item não tem mínimo próprio
    assert linha.faltam == 1
    assert "KIT.MAOPE.ROSA" in linha.porque and "kit.combo" in linha.porque


def test_quantidade_por_kit_multiplica_a_reserva(session, com_estoque):
    """`kit.combo` leva 2 embalagens: mínimo 50 no kit pede 100 embalagens."""
    com_estoque["kit.combo"].estoque_minimo = 50
    session.commit()

    linha = _por_sku(compras.lista_de_compras(session))["embalagem"]
    assert linha.reservado_para_kits == 100               # 50 × 2
    assert linha.saldo == 80
    assert linha.faltam == 20
    assert "× 2 por kit" in linha.porque


def test_kit_sem_minimo_nao_reserva_nada(session, com_estoque):
    """Kit sem mínimo continua listado como travado, mas não puxa compra."""
    com_estoque["mord.pe.rosa"].estoque_minimo = 6        # 6 em estoque: no limite
    session.commit()

    linha = _por_sku(compras.lista_de_compras(session))["mord.pe.rosa"]
    assert linha.reservado_para_kits == 0
    assert [k.sku for k in linha.trava_kits] == ["KIT.MAOPE.ROSA"]


def test_kit_arquivado_para_de_reservar(session, com_estoque):
    """Kit fora do catálogo não pode continuar puxando compra (§6)."""
    kit = com_estoque["KIT.MAOPE.ROSA"]
    kit.estoque_minimo = 20
    session.commit()
    assert "mord.pe.rosa" in _por_sku(compras.lista_de_compras(session))

    exclusao.arquivar(session, kit)
    session.commit()
    assert "mord.pe.rosa" not in _por_sku(compras.lista_de_compras(session))


def test_kit_nunca_aparece_na_lista(session, com_estoque):
    """Quem se compra é o componente: kit é montado, não comprado (§4.2)."""
    com_estoque["KIT.MAOPE.ROSA"].estoque_minimo = 30
    session.commit()

    skus = _por_sku(compras.lista_de_compras(session))
    assert "KIT.MAOPE.ROSA" not in skus
    assert "mord.mao.rosa" in skus and "mord.pe.rosa" in skus


def test_saldo_negativo_entra_mesmo_sem_minimo(session, com_estoque):
    """Já saiu mais do que existia: isso é compra pendente por definição."""
    ledger.aplicar_venda(session, com_estoque["mord.pe.rosa"], 10, referencia_externa="V1")
    session.commit()

    linha = _por_sku(compras.lista_de_compras(session))["mord.pe.rosa"]
    assert linha.saldo == -4
    assert linha.faltam == 4
    assert linha.porque == "estoque negativo"


def test_mais_urgente_primeiro(session, com_estoque):
    com_estoque["manta.rosa"].estoque_minimo = 6          # tem 5 → faltam 1
    com_estoque["mord.pe.rosa"].estoque_minimo = 30       # tem 6 → faltam 24
    session.commit()

    linhas = compras.lista_de_compras(session)
    assert [n.produto.sku for n in linhas[:2]] == ["mord.pe.rosa", "manta.rosa"]


def test_custo_estimado_usa_o_custo_do_item(session, com_estoque):
    com_estoque["manta.rosa"].estoque_minimo = 9          # tem 5 → faltam 4 × R$ 11,90
    session.commit()

    linhas = compras.lista_de_compras(session)
    assert _por_sku(linhas)["manta.rosa"].custo_estimado == 47.60
    assert compras.total_estimado(linhas) == 47.60


def test_exportar_csv_traz_a_conta_inteira(session, com_estoque, tmp_path):
    item = com_estoque["mord.mao.rosa"]
    ledger.entrada_compra(session, item, 1)               # 15
    item.estoque_minimo = 10
    com_estoque["KIT.MAOPE.ROSA"].estoque_minimo = 10
    session.commit()

    destino, quantos = compras.exportar_csv(session, tmp_path / "compras.csv")
    assert quantos >= 1
    texto = destino.read_text(encoding="utf-8-sig")

    linha = next(ln for ln in texto.splitlines() if ln.startswith("mord.mao.rosa;"))
    campos = linha.split(";")
    assert campos[2:7] == ["15", "10", "10", "20", "5"]   # tem, mín, kits, alvo, comprar
    assert "Custo estimado total (R$)" in texto


def test_exportar_csv_sem_nada_para_comprar(session, com_estoque, tmp_path):
    destino, quantos = compras.exportar_csv(session, tmp_path / "compras.csv")
    assert quantos == 0
    assert "Itens na lista;0" in destino.read_text(encoding="utf-8-sig")
