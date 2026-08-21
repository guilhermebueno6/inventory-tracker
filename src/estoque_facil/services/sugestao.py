"""Sugestão de componentes por nome — ESCOPO.md §5.2.2.

Os SKUs dela são descritivos (`kit.mantamordedorazul`), e casar esses pedaços
contra os produtos simples põe os candidatos certos no topo. Não acerta sozinho:
sugere, e ela decide.

Inferir composição pelo CUSTO foi medido e descartado — Anexo B do escopo.
"""
from __future__ import annotations

import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.models import Produto, TipoProduto

TAMANHO_MINIMO_TOKEN = 3
PREFIXO_COMPARADO = 4


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _tokens(texto: str) -> set[str]:
    limpo = _sem_acento(texto).replace("+", ".").replace(" ", ".").replace("_", ".")
    return {t for t in limpo.split(".") if len(t) >= TAMANHO_MINIMO_TOKEN}


def _alvo(produto: Produto) -> str:
    return _sem_acento(f"{produto.sku} {produto.nome or ''}").replace(".", "").replace("+", "")


def sugerir_componentes(
    session: Session, kit: Produto, limite: int = 8
) -> list[tuple[float, Produto]]:
    """Produtos simples ordenados pela fração de tokens que aparecem no nome do kit."""
    alvo = _alvo(kit)
    simples = session.scalars(
        select(Produto).where(
            Produto.tipo == TipoProduto.SIMPLES, Produto.ativo.is_(True)
        )
    ).all()

    pontuados: list[tuple[float, Produto]] = []
    for p in simples:
        tokens = _tokens(f"{p.sku} {p.nome or ''}")
        if not tokens:
            continue
        acertos = sum(1 for t in tokens if t[:PREFIXO_COMPARADO] in alvo)
        if acertos:
            pontuados.append((acertos / len(tokens), p))

    pontuados.sort(key=lambda par: (-par[0], par[1].sku))
    return pontuados[:limite]
