"""Carga inicial do catálogo — ESCOPO.md §5.3 passo 1.

O arquivo real dela: `CUSTO;IMPOSTO;SKU`, separador `;`, decimal `.`, UTF-8, 195 SKUs.
Não traz nome de produto — os nomes vêm depois, do relatório de vendas (passo 2).

O leitor aceita variações de cabeçalho e separador porque planilha exportada
raramente sai duas vezes igual.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

ALIASES = {
    "sku": {"sku", "codigo", "código", "cod", "referencia", "referência"},
    "custo": {"custo", "preco de custo", "preço de custo", "custo unitario"},
    "imposto": {"imposto", "tributo", "aliquota", "alíquota"},
    "nome": {"nome", "descricao", "descrição", "titulo", "título", "produto"},
    "estoque": {"estoque", "quantidade", "qtd", "saldo"},
    "minimo": {"minimo", "mínimo", "estoque minimo", "estoque mínimo"},
}


class ErroCatalogo(Exception):
    pass


@dataclass
class LinhaCatalogo:
    sku: str
    nome: str = ""
    custo: float = 0.0
    imposto: float = 0.0
    estoque: int | None = None
    minimo: int = 0
    provavel_kit: bool = False
    linha: int = 0


@dataclass
class Catalogo:
    linhas: list[LinhaCatalogo]
    arquivo: str
    avisos: list[str] = field(default_factory=list)

    @property
    def kits(self) -> list[LinhaCatalogo]:
        return [ln for ln in self.linhas if ln.provavel_kit]


def parece_kit(sku: str, nome: str = "") -> bool:
    """Heurística da §5.3 passo 3. SUGERE — a usuária confirma em lote."""
    alvo = f"{sku} {nome}".lower()
    return "kit" in alvo or "+" in alvo


def _numero(txt: str) -> float:
    txt = (txt or "").strip()
    if not txt:
        return 0.0
    # aceita 1.234,56 e 1234.56
    if "," in txt and "." in txt:
        txt = txt.replace(".", "").replace(",", ".")
    else:
        txt = txt.replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _detectar_separador(amostra: str) -> str:
    try:
        return csv.Sniffer().sniff(amostra, delimiters=";,\t").delimiter
    except csv.Error:
        return ";" if amostra.count(";") >= amostra.count(",") else ","


def _mapear_colunas(campos: list[str]) -> dict[str, str]:
    mapa = {}
    for campo in campos:
        chave = (campo or "").strip().lower().lstrip("﻿")
        for destino, nomes in ALIASES.items():
            if chave in nomes and destino not in mapa:
                mapa[destino] = campo
    return mapa


def ler(caminho: str | Path) -> Catalogo:
    caminho = Path(caminho)
    try:
        texto = caminho.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        texto = caminho.read_text(encoding="latin-1")

    if not texto.strip():
        raise ErroCatalogo("O arquivo está vazio.")

    sep = _detectar_separador(texto[:2000])
    leitor = csv.DictReader(io.StringIO(texto), delimiter=sep)
    if not leitor.fieldnames:
        raise ErroCatalogo("Não consegui ler o cabeçalho do arquivo.")

    mapa = _mapear_colunas(list(leitor.fieldnames))
    if "sku" not in mapa:
        raise ErroCatalogo(
            "Não encontrei a coluna de código do produto (SKU).\n\n"
            f"Colunas encontradas: {', '.join(leitor.fieldnames)}"
        )

    linhas: list[LinhaCatalogo] = []
    avisos: list[str] = []
    vistos: set[str] = set()

    for n, row in enumerate(leitor, start=2):
        sku = (row.get(mapa["sku"]) or "").strip()
        if not sku:
            continue
        chave = sku.lower()
        if chave in vistos:
            avisos.append(f"Linha {n}: código {sku} repetido — usei o primeiro.")
            continue
        vistos.add(chave)

        nome = (row.get(mapa["nome"], "") or "").strip() if "nome" in mapa else ""
        estoque = None
        if "estoque" in mapa:
            bruto = (row.get(mapa["estoque"]) or "").strip()
            if bruto:
                estoque = int(_numero(bruto))

        linhas.append(
            LinhaCatalogo(
                sku=sku,
                nome=nome,
                custo=_numero(row.get(mapa.get("custo", ""), "")),
                imposto=_numero(row.get(mapa.get("imposto", ""), "")),
                estoque=estoque,
                minimo=int(_numero(row.get(mapa.get("minimo", ""), ""))),
                provavel_kit=parece_kit(sku, nome),
                linha=n,
            )
        )

    if not linhas:
        raise ErroCatalogo("Não encontrei nenhum produto no arquivo.")
    return Catalogo(linhas=linhas, arquivo=caminho.name, avisos=avisos)
