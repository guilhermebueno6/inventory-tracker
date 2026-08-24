# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller — modo onedir (ESCOPO.md §9.1).

onedir e não onefile: abre bem mais rápido e o antivírus reclama menos.
"""
import sys
from pathlib import Path

RAIZ = Path(SPECPATH).parent
SRC = RAIZ / "src"

a = Analysis(
    # launcher.py e NÃO estoque_facil/__main__.py: ver o comentário no launcher
    [str(RAIZ / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        (str(SRC / "estoque_facil" / "ui" / "style.qss"), "estoque_facil/ui"),
        # sem as migrações empacotadas, o app não consegue evoluir o banco
        (str(SRC / "estoque_facil" / "migracoes"), "estoque_facil/migracoes"),
        # a marca: fonte Archivo, símbolo, lockups e as setas do QSS. Sem esta
        # pasta o app abre com a fonte do sistema e sem ícone — e o teste de
        # fumaça (`--verificar`) é o que pega isso antes do instalador sair.
        (str(SRC / "estoque_facil" / "resources"), "estoque_facil/resources"),
    ],
    hiddenimports=["estoque_facil", "alembic", "sqlalchemy.dialects.sqlite"],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

RECURSOS = SRC / "estoque_facil" / "resources"
ICONE = RECURSOS / ("icone.icns" if sys.platform == "darwin" else "icone.ico")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EstoqueFacil",
    console=False,
    icon=str(ICONE) if ICONE.exists() else None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="EstoqueFacil")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Estoque Facil.app",
        icon=str(ICONE) if ICONE.exists() else None,
        bundle_identifier="com.guilhermebueno.estoquefacil",
        info_plist={
            "CFBundleName": "Estoque Fácil",
            "CFBundleDisplayName": "Estoque Fácil",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
