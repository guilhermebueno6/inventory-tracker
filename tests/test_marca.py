"""Guardas do sistema visual — manual da marca §01 a §05.

Não testam aparência: testam o que quebra em silêncio e só aparece na máquina
dela — a fonte que não foi empacotada, um token de cor que ficou sem substituir,
um hex solto que escapou da paleta.
"""
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from estoque_facil.ui import marca  # noqa: E402

UI = Path(marca.__file__).parent


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------- fonte


def test_a_fonte_archivo_esta_empacotada_e_registra(app):
    """Se cair no fallback, o app abre com a letra do sistema — não é a marca."""
    fontes = marca.RECURSOS / "fontes"
    for peso in ("Regular", "SemiBold", "Bold"):
        assert (fontes / f"Archivo-{peso}.ttf").exists(), f"falta o peso {peso}"
    assert marca.familia() == "Archivo"


def _tinta(fonte) -> int:
    """Quanto preto a fonte põe na tela ao escrever a mesma frase.

    Medir o desenho é o único jeito honesto de testar peso: pedir 700 e receber
    700 de volta não prova nada — o Qt devolve o que foi pedido mesmo quando
    caiu num peso que não existe.
    """
    from PySide6.QtGui import QImage, QPainter

    imagem = QImage(520, 70, QImage.Format_Grayscale8)
    imagem.fill(255)
    pintor = QPainter(imagem)
    pintor.setFont(fonte)
    pintor.drawText(10, 48, "Estoque Facil 123")
    pintor.end()
    return sum(
        255 - imagem.pixelColor(x, y).red()
        for y in range(imagem.height())
        for x in range(imagem.width())
    )


def test_os_pesos_do_manual_desenham_diferente(app):
    """400/600/700 precisam DESENHAR diferente, não só pedir peso diferente.

    Foi por não medir isto que a primeira versão passou no macOS e quebrou no
    Linux: a fonte variável do Google Fonts tem 600 como padrão do eixo `wght`,
    e sobre fontconfig os três pesos saíam do mesmo desenho. Com os três
    estáticos empacotados, a tinta tem que crescer a cada degrau.
    """
    from PySide6.QtGui import QFontInfo

    fontes = {peso: marca.fonte(20, peso) for peso in (400, 600, 700)}
    assert all(QFontInfo(f).family() == "Archivo" for f in fontes.values()), (
        "algum peso caiu na fonte do sistema"
    )

    tinta = {peso: _tinta(f) for peso, f in fontes.items()}
    assert tinta[400] < tinta[600] < tinta[700], tinta


def test_numero_de_tabela_usa_algarismo_tabular(app):
    """Manual §04: sem `tnum`, o "1" é mais estreito e a coluna desalinha."""
    from PySide6.QtGui import QFontMetrics

    tabular = QFontMetrics(marca.fonte_tabular(14))
    assert tabular.horizontalAdvance("1111") == tabular.horizontalAdvance("8888")


# -------------------------------------------------------------------- cor


def test_a_paleta_e_a_do_manual():
    assert marca.VERMELHO == "#EC3013"
    assert marca.VERMELHO_ESCURO == "#B32309"
    assert marca.TINTA == "#201E1D"
    assert marca.FUNDO == "#F3F2F2"
    assert marca.SUPERFICIE == "#FFFFFF"
    assert marca.CINZA == "#6F6863"


def test_nenhuma_cor_solta_fora_do_modulo_da_marca():
    """Um hex escrito à mão numa tela é como a paleta se desfaz com o tempo."""
    hex_solto = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    fugitivos = {}
    for arquivo in list(UI.rglob("*.py")):
        if arquivo.name == "marca.py":
            continue
        achados = hex_solto.findall(arquivo.read_text(encoding="utf-8"))
        if achados:
            fugitivos[arquivo.name] = achados
    assert not fugitivos, f"cor fora da paleta: {fugitivos}"


# ------------------------------------------------------------ folha de estilo


def test_a_folha_de_estilo_nao_deixa_token_por_substituir():
    css = marca.folha_de_estilo()
    assert css, "style.qss não foi encontrado no pacote"
    sobrando = re.findall(r"@[A-Z_]+@", css)
    assert not sobrando, f"token sem valor: {sorted(set(sobrando))}"


def test_a_folha_de_estilo_nao_tem_canto_arredondado():
    """Manual §05, 'o que não fazer': arredondar os cantos."""
    css = marca.folha_de_estilo()
    raios = re.findall(r"border-radius:\s*([^;]+);", css)
    assert raios, "o QSS precisa zerar o raio explicitamente"
    assert all(r.strip() == "0" for r in raios), f"raio diferente de zero: {raios}"


def test_todo_arquivo_citado_pela_folha_de_estilo_existe():
    """`url()` apontando para arquivo ausente vira controle sem seta nenhuma."""
    for referencia in re.findall(r"url\(([^)]+)\)", marca.folha_de_estilo()):
        assert Path(referencia).exists(), f"o QSS aponta para {referencia}"


# ----------------------------------------------------------------- símbolo


def _barras(mapa):
    """Conta as faixas verticais claras na altura do meio do símbolo."""
    imagem = mapa.toImage()
    y = imagem.height() // 2
    faixas, dentro = 0, False
    for x in range(imagem.width()):
        clara = imagem.pixelColor(x, y).lightness() > 160
        if clara and not dentro:
            faixas += 1
        dentro = clara
    return faixas


def test_o_simbolo_grande_tem_as_quatro_barras(app):
    assert _barras(marca.simbolo(96)) == 4


def test_abaixo_de_24px_o_simbolo_usa_a_variante_de_tres_barras(app):
    """Manual §01: abaixo de 24 px as quatro barras viram borrão."""
    assert _barras(marca.simbolo(16)) == 3
    assert _barras(marca.simbolo(marca.LIMITE_3_BARRAS)) == 4


def test_as_barras_nunca_tem_a_mesma_largura():
    """É o ritmo desigual que faz o símbolo ler como código de barras (§01)."""
    for grupo in (marca.BARRAS, marca.BARRAS_3):
        larguras = [largura for _x, largura in grupo]
        assert len(set(larguras)) == len(larguras), larguras


# ------------------------------------------------------------------- ícone


def test_o_icone_do_app_cobre_os_tamanhos_do_kit(app):
    """Windows pede 16/32/48/256; macOS vai até 1024 (LEIA-ME do kit)."""
    tamanhos = {s.width() for s in marca.icone_do_app().availableSizes()}
    assert {16, 32, 48, 256, 512, 1024} <= tamanhos


def test_os_icones_de_instalador_existem():
    """Sem eles o executável sai com o ícone genérico do PyInstaller."""
    assert (marca.RECURSOS / "icone.ico").exists()
    assert (marca.RECURSOS / "icone.icns").exists()
