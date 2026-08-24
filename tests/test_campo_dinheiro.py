"""O campo de valor fala a mesma língua do resto do aplicativo — ESCOPO.md §6.

O que importa aqui não é o widget: é que ela veja "R$ 13,50" onde o balanço
escreve "R$ 13,50", e que o que ela digitar entre do jeito que ela digitou.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QValidator  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from estoque_facil.ui.widgets.comuns import CampoDinheiro, ler_dinheiro, moeda  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("digitado, esperado", [
    ("13,50", 13.50),           # como ela escreve
    ("R$ 13,50", 13.50),        # com o prefixo que o campo já mostra
    ("13.50", 13.50),           # ponto do teclado numérico
    ("13", 13.0),
    ("13,", 13.0),              # no meio da digitação
    (",50", 0.50),
    ("0,05", 0.05),
    ("1.234,56", 1234.56),      # os dois separadores: o último é o centavo
    ("1,234.56", 1234.56),      # invertido, mesma regra
    ("1.234", 1234.0),          # ponto sozinho separando três dígitos: milhar
    ("1.234.567", 1234567.0),
    ("9.999", 9999.0),
    ("1.5", 1.50),              # ponto sozinho, um dígito: centavo
    ("R$ ", 0.0),               # campo vazio
    ("", 0.0),
    ("-13,50", -13.50),
])
def test_le_o_que_ela_digitou(digitado, esperado):
    assert ler_dinheiro(digitado) == pytest.approx(esperado)


@pytest.mark.parametrize("valor", [0.0, 0.05, 13.50, 1234.56, 999999.0])
def test_o_campo_escreve_igual_ao_resto_do_app(app, valor):
    campo = CampoDinheiro(maximo=9999999)
    campo.setValue(valor)
    assert campo.text() == moeda(valor)


@pytest.mark.parametrize("digitado, esperado", [
    ("13,50", 13.50),
    ("13.50", 13.50),
    ("1.234,56", 1234.56),
    ("R$ 1.234,56", 1234.56),
])
def test_digitar_no_campo_chega_no_valor(app, digitado, esperado):
    """Ida e volta pelo widget: o texto vira número e o número volta em pt-BR."""
    campo = CampoDinheiro(maximo=9999999)
    campo.lineEdit().setText(digitado)
    campo.interpretText()
    assert campo.value() == pytest.approx(esperado)
    assert campo.text() == moeda(esperado)


def test_teclas_do_valor_passam_e_letra_nao(app):
    campo = CampoDinheiro()
    estado_ok, _, _ = campo.validate("R$ 13,50", 8)
    assert estado_ok == QValidator.Acceptable
    # ainda sem número nenhum: é começo de edição, não erro
    estado_meio, _, _ = campo.validate("R$ ", 3)
    assert estado_meio == QValidator.Intermediate
    estado_ruim, _, _ = campo.validate("R$ 13x", 6)
    assert estado_ruim == QValidator.Invalid


def test_o_campo_respeita_o_maximo(app):
    campo = CampoDinheiro(maximo=999999)
    campo.lineEdit().setText("9.999.999,00")
    campo.interpretText()
    assert campo.value() == pytest.approx(999999.0)
