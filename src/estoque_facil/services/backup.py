"""Backup em CSV — ESCOPO.md §7.1.

CSV porque ela abre no Excel e entende. O .db vai junto porque é o que restaura
100% fiel. A tabela `composicao` é a mais importante do backup: é o que custou
mais tempo para montar.
"""
from __future__ import annotations

import csv
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from ..core.db import caminho_banco, copiar_banco, pasta_dados
from ..core.models import Base, Composicao, Produto, Saldo

RETENCAO_DIAS = 30
TABELAS = ["produto", "composicao", "saldo", "movimento", "local_estoque",
           "lote_importacao", "vinculo_ml", "config", "venda_item", "despesa"]


def _escrever_tabela(session: Session, nome: str, destino: Path) -> int:
    tabela = Base.metadata.tables[nome]
    linhas = session.execute(select(tabela)).mappings().all()
    with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow([c.name for c in tabela.columns])
        for linha in linhas:
            w.writerow([linha[c.name] for c in tabela.columns])
    return len(linhas)


def _estoque_legivel(session: Session, destino: Path) -> None:
    """Uma planilha que ela consegue ler sem saber o que é uma tabela."""
    from ..core.kits import componentes_de, disponivel

    with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Código", "Produto", "Tipo", "Em estoque", "Mínimo", "Custo",
                    "Composição"])
        for p in session.scalars(select(Produto).order_by(Produto.tipo, Produto.sku)).all():
            comp = ""
            if p.eh_kit:
                comp = " + ".join(
                    f"{c.quantidade}x {c.componente.sku}" if c.quantidade > 1
                    else c.componente.sku
                    for c in componentes_de(session, p)
                )
            w.writerow([
                p.sku, p.nome, "Kit" if p.eh_kit else "Item",
                disponivel(session, p).quantidade, p.estoque_minimo,
                f"{p.custo:.2f}".replace(".", ","), comp,
            ])


def gerar(session: Session, pasta: Path | None = None, *, incluir_db: bool = True) -> Path:
    """Cria uma pasta de backup com um CSV por tabela + a planilha legível."""
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M")
    base = Path(pasta) if pasta else pasta_dados() / "backups"
    destino = base / carimbo
    destino.mkdir(parents=True, exist_ok=True)

    existentes = set(inspect(session.get_bind()).get_table_names())
    for nome in TABELAS:
        if nome in existentes:
            _escrever_tabela(session, nome, destino / f"{nome}.csv")
    _estoque_legivel(session, destino / "estoque.csv")

    if incluir_db:
        origem = caminho_banco()
        if origem.exists():
            # copiar_banco e não shutil: o .db sozinho perde o que está no WAL
            copiar_banco(destino / "estoque.db", origem)
    return destino


def gerar_zip(session: Session, destino_zip: Path) -> Path:
    """Backup manual: um .zip só, que ela guarda onde quiser (§7.1)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        pasta = gerar(session, Path(tmp))
        destino_zip = Path(destino_zip)
        destino_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for arquivo in pasta.iterdir():
                z.write(arquivo, arquivo.name)
    return destino_zip


def limpar_antigos(dias: int = RETENCAO_DIAS) -> int:
    limite = datetime.now() - timedelta(days=dias)
    pasta = pasta_dados() / "backups"
    removidos = 0
    for item in pasta.iterdir() if pasta.exists() else []:
        if not item.is_dir():
            continue
        try:
            quando = datetime.strptime(item.name[:15], "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if quando < limite:
            shutil.rmtree(item, ignore_errors=True)
            removidos += 1
    return removidos


def resumo(session: Session) -> dict:
    produtos = session.scalar(select(Produto.id).limit(1))
    return {
        "produtos": len(session.scalars(select(Produto.id)).all()),
        "composicoes": len(session.scalars(select(Composicao.id)).all()),
        "saldos": len(session.scalars(select(Saldo.id)).all()),
        "tem_dados": produtos is not None,
    }
