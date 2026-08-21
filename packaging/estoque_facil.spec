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
    ],
    hiddenimports=["estoque_facil", "alembic", "sqlalchemy.dialects.sqlite"],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EstoqueFacil",
    console=False,
    icon=str(RAIZ / "src" / "estoque_facil" / "resources" / "icone.ico")
    if (RAIZ / "src" / "estoque_facil" / "resources" / "icone.ico").exists() else None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="EstoqueFacil")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Estoque Facil.app",
        bundle_identifier="com.guilhermebueno.estoquefacil",
        info_plist={
            "CFBundleName": "Estoque Fácil",
            "CFBundleDisplayName": "Estoque Fácil",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
