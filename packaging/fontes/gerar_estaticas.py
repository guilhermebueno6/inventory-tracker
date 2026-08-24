"""Gera os pesos estáticos do Archivo a partir da fonte variável do Google Fonts.

Por que não empacotar a variável direto: o Qt no Linux lê o nameID 1 dela, que
é "Archivo SemiBold" — o eixo `wght` tem 600 como padrão. Resultado: os pesos
400, 500 e 600 saíam idênticos (todos no padrão) e o 700 virava negrito
sintético, em vez do Bold desenhado. No macOS o Qt lê as instâncias do `fvar` e
funcionava, o que fazia o problema aparecer só no Linux.

Três arquivos estáticos resolvem em qualquer backend: cada um registra como um
estilo normal da família "Archivo".

Uso (só quando a fonte for atualizada — o resultado é versionado):

    pip install fonttools
    python packaging/fontes/gerar_estaticas.py caminho/para/Archivo[wdth,wght].ttf
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Só os pesos que o manual da marca §04 usa. Cada arquivo a mais é peso morto
# no instalador.
PESOS = {400: "Regular", 600: "SemiBold", 700: "Bold"}
LARGURA = 100          # a marca não usa o eixo de largura
DESTINO = Path(__file__).resolve().parents[2] / "src/estoque_facil/resources/fontes"


def gerar(variavel: Path) -> None:
    for peso, estilo in PESOS.items():
        fonte = instancer.instantiateVariableFont(
            TTFont(variavel),
            {"wght": peso, "wdth": LARGURA},
            updateFontNames=True,     # sem isto o nome continua "Archivo SemiBold"
            inplace=True,
        )
        saida = DESTINO / f"Archivo-{estilo}.ttf"
        fonte.save(saida)
        nomes = {r.nameID: str(r) for r in fonte["name"].names if r.platformID == 3}
        print(f"{saida.name}: família {nomes.get(1)!r}, estilo {nomes.get(2)!r}, "
              f"{saida.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    gerar(Path(sys.argv[1]))
