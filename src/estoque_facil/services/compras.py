"""Lista de compras — o que precisa entrar no estoque (ESCOPO.md §5.2.4).

Um item entra na lista quando o estoque está **igual ou abaixo** do que ele
precisa ter. E o que ele precisa ter não é só o mínimo dele: é o mínimo dele
MAIS o que os kits reservam.

    precisa_ter(item) = minimo(item) + Σ  minimo(kit) × quantidade_por_kit

Sem essa soma, o mínimo definido no kit não significaria nada — e é justamente
onde a conta na mão erra. Com mínimo 10 no item e mínimo 10 num kit que usa 1
unidade dele, 15 em estoque JÁ É pouco: dá para segurar o item ou o kit, não os
dois. A lista mostra 20 como alvo e pede 5.

O mesmo item pode ser puxado por vários kits, e é aí que a conta manual desiste:
`mord.mao.rosa` está em `KIT.MAOPE.ROSA` e em `kit.combo`, e o que ele precisa
ter é a soma dos dois mínimos.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.db import local_id
from ..core.models import CASA, Composicao, Produto, Saldo, TipoProduto


@dataclass(frozen=True)
class DemandaDeKit:
    """Quanto de um item um kit reserva para conseguir manter o próprio mínimo."""

    kit: Produto
    por_kit: int

    @property
    def minimo(self) -> int:
        return max(self.kit.estoque_minimo or 0, 0)

    @property
    def unidades(self) -> int:
        """Kit sem mínimo definido não reserva nada — só entra como kit travado."""
        return self.minimo * self.por_kit


@dataclass
class Necessidade:
    """Uma linha da lista de compras."""

    produto: Produto
    saldo: int
    kits: list[DemandaDeKit] = field(default_factory=list)

    @property
    def minimo_proprio(self) -> int:
        return max(self.produto.estoque_minimo or 0, 0)

    @property
    def kits_que_pedem(self) -> list[DemandaDeKit]:
        return [d for d in self.kits if d.unidades > 0]

    @property
    def reservado_para_kits(self) -> int:
        return sum(d.unidades for d in self.kits)

    @property
    def precisa_ter(self) -> int:
        return self.minimo_proprio + self.reservado_para_kits

    @property
    def faltam(self) -> int:
        """Quanto comprar para sair do limite. Zero = está exatamente no limite."""
        return max(self.precisa_ter - self.saldo, 0)

    @property
    def custo_estimado(self) -> float:
        return round(self.faltam * (self.produto.custo or 0.0), 2)

    @property
    def porque(self) -> str:
        """A conta escrita por extenso — é o que ela confere antes de comprar."""
        partes = []
        if self.minimo_proprio:
            partes.append(f"mínimo do item: {self.minimo_proprio}")
        for d in self.kits_que_pedem:
            partes.append(
                f"{d.kit.sku}: {d.unidades} "
                f"(mínimo {d.minimo} × {d.por_kit} por kit)"
            )
        if not partes:
            return "estoque negativo"
        return "; ".join(partes)

    @property
    def trava_kits(self) -> list[Produto]:
        """Kits que param de ser montáveis quando este item acaba (§5.2.4)."""
        return [d.kit for d in self.kits]


def _demandas_por_componente(session: Session) -> dict[int, list[DemandaDeKit]]:
    """Todas as composições de uma vez — 195 itens × 75 kits não pede consulta por item."""
    saida: dict[int, list[DemandaDeKit]] = {}
    for c in session.scalars(select(Composicao)).all():
        if c.kit is None or not c.kit.ativo:
            continue
        saida.setdefault(c.componente_id, []).append(DemandaDeKit(c.kit, c.quantidade))
    for lista in saida.values():
        lista.sort(key=lambda d: (-d.unidades, d.kit.sku))
    return saida


def lista_de_compras(session: Session, local_codigo: str = CASA) -> list[Necessidade]:
    """Itens iguais ou abaixo do que precisam ter, os mais urgentes primeiro.

    Só produtos SIMPLES: kit não tem estoque, quem se compra é o componente.
    Um kit abaixo do mínimo aparece aqui pelo componente que o está travando —
    que é o item que ela precisa pôr no carrinho.
    """
    lid = local_id(session, local_codigo)
    saldos = dict(
        session.execute(
            select(Saldo.produto_id, Saldo.quantidade).where(Saldo.local_id == lid)
        ).all()
    )
    demandas = _demandas_por_componente(session)

    produtos = session.scalars(
        select(Produto).where(
            Produto.ativo.is_(True), Produto.tipo == TipoProduto.SIMPLES
        )
    ).all()

    saida: list[Necessidade] = []
    for p in produtos:
        n = Necessidade(
            produto=p,
            saldo=int(saldos.get(p.id, 0)),
            kits=demandas.get(p.id, []),
        )
        # Negativo entra mesmo sem mínimo nenhum: já saiu mais do que existia,
        # e isso é uma compra pendente por definição.
        no_limite = n.precisa_ter > 0 and n.saldo <= n.precisa_ter
        if no_limite or n.saldo < 0:
            saida.append(n)

    saida.sort(key=lambda n: (-n.faltam, -len(n.kits), n.produto.sku))
    return saida


def total_estimado(linhas: list[Necessidade]) -> float:
    return round(sum(n.custo_estimado for n in linhas), 2)


def _br(valor: float, casas: int = 2) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def exportar_csv(
    session: Session, destino: Path | str, local_codigo: str = CASA
) -> tuple[Path, int]:
    """Grava a lista de compras. Devolve (caminho, quantos itens)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    linhas = lista_de_compras(session, local_codigo)

    with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Lista de compras", f"{datetime.now():%d/%m/%Y %H:%M}"])
        w.writerow([])
        w.writerow([
            "Código", "Produto", "Tem hoje", "Mínimo do item",
            "Reservado para kits", "Precisa ter", "Comprar",
            "Custo unitário (R$)", "Custo estimado (R$)",
            "Fornecedor", "Trava kits", "Por quê",
        ])
        for n in linhas:
            w.writerow([
                n.produto.sku,
                n.produto.rotulo,
                n.saldo,
                n.minimo_proprio,
                n.reservado_para_kits,
                n.precisa_ter,
                n.faltam,
                _br(n.produto.custo or 0.0),
                _br(n.custo_estimado),
                n.produto.fornecedor or "",
                len(n.trava_kits),
                n.porque,
            ])
        w.writerow([])
        w.writerow(["Itens na lista", len(linhas)])
        w.writerow(["Custo estimado total (R$)", _br(total_estimado(linhas))])
    return destino, len(linhas)
