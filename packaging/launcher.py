# -*- coding: utf-8 -*-
"""Ponto de entrada do executável empacotado.

Existe por um motivo específico: o PyInstaller executa o script principal como
módulo solto (`__main__`), sem pacote pai. Apontar o spec direto para
`estoque_facil/__main__.py` fazia o app empacotado morrer na primeira linha com
"attempted relative import with no known parent package" — o build passava e só
quebrava na máquina do usuário.

Importando o pacote pelo nome, os imports relativos de dentro dele funcionam.
"""
import sys

from estoque_facil.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
