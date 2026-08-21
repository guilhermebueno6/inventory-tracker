"""Kits: disponibilidade, explosão e cascata — ESCOPO.md §4.2 e §5.2.

A regra que sustenta o app inteiro:

    KIT NÃO TEM ESTOQUE PRÓPRIO.

Os kits dela são montados na hora do envio, então o que existe fisicamente são
os componentes. Disponibilidade de kit é derivada:

    disponivel(kit) = min( saldo(componente) // quantidade_necessaria )
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CASA, Composicao, Produto, Saldo, TipoProduto


class ErroComposicao(Exception):
    """Composição inválida. A mensagem é mostrada à usuária como está."""


@dataclass
class ItemExplodido:
    """Uma baixa concreta de componente, com o kit que a originou."""

    produto: Produto
    quantidade: int
    vendido_como: Produto | None = None      # o kit, quando veio de um

    @property
    def por_kit(self) -> bool:
        return self.vendido_como is not None


@dataclass
class Disponibilidade:
    quantidade: int
    gargalo: Produto | None = None
    detalhes: list[tuple[Produto, int, int]] = field(default_factory=list)  # comp, saldo, precisa


def componentes_de(session: Session, kit: Produto) -> list[Composicao]:
    """Lê a composição SEMPRE do banco.

    A sessão usa expire_on_commit=False (para os objetos seguirem utilizáveis na
    interface depois do commit), e isso deixa `kit.componentes` obsoleto em memória
    logo depois de uma alteração. Consultar direto elimina a classe inteira de bug.
    """
    return list(
        session.scalars(select(Composicao).where(Composicao.kit_id == kit.id)).all()
    )


def saldo_simples(session: Session, produto: Produto, local_codigo: str = CASA) -> int:
    from .db import local_id

    if produto.eh_kit:
        raise ErroComposicao(f"{produto.rotulo} é um kit e não tem estoque próprio.")
    lid = local_id(session, local_codigo)
    s = session.scalar(
        select(Saldo).where(Saldo.produto_id == produto.id, Saldo.local_id == lid)
    )
    return s.quantidade if s else 0


def disponivel(session: Session, produto: Produto, local_codigo: str = CASA) -> Disponibilidade:
    """Quantos dá para vender/montar hoje."""
    if not produto.eh_kit:
        return Disponibilidade(quantidade=saldo_simples(session, produto, local_codigo))

    comps = componentes_de(session, produto)
    if not comps:
        # Kit sem composição não tem disponibilidade definida. Nunca deve chegar aqui
        # (a UI impede salvar vazio), mas 0 é a resposta segura.
        return Disponibilidade(quantidade=0)

    detalhes: list[tuple[Produto, int, int]] = []
    for c in comps:
        detalhes.append((c.componente, saldo_simples(session, c.componente, local_codigo),
                         c.quantidade))

    possiveis = [(saldo // precisa, comp) for comp, saldo, precisa in detalhes]
    qtd, gargalo = min(possiveis, key=lambda p: p[0])
    return Disponibilidade(quantidade=max(qtd, 0), gargalo=gargalo, detalhes=detalhes)


def explodir(session: Session, produto: Produto, quantidade: int) -> list[ItemExplodido]:
    """Transforma uma venda em baixas de componentes. ESCOPO.md §5.1 passo 4.

    Produto simples devolve ele mesmo — quem chama não precisa saber a diferença.
    """
    if quantidade <= 0:
        raise ErroComposicao("Quantidade precisa ser maior que zero.")
    if not produto.eh_kit:
        return [ItemExplodido(produto=produto, quantidade=quantidade)]

    comps = componentes_de(session, produto)
    if not comps:
        raise ErroComposicao(
            f"O kit {produto.rotulo} ainda não tem composição. "
            "Defina de que ele é montado antes de dar baixa."
        )
    return [
        ItemExplodido(produto=c.componente, quantidade=c.quantidade * quantidade,
                      vendido_como=produto)
        for c in comps
    ]


def kits_afetados(session: Session, componente: Produto) -> list[Produto]:
    """Quais kits travam se este componente acabar (alerta em cascata — §5.2.4)."""
    linhas = session.scalars(
        select(Composicao).where(Composicao.componente_id == componente.id)
    ).all()
    return [c.kit for c in linhas]


def conferir_custo(session: Session, produto: Produto) -> tuple[bool, float, float, str]:
    """O custo do kit bate com a soma dos componentes? ESCOPO.md §5.2.3.

    Isto CONFERE, não descobre — inferir composição por custo foi medido e
    descartado (Anexo B do escopo). Aviso, nunca bloqueio.
    """
    comps = componentes_de(session, produto) if produto.eh_kit else []
    if not comps:
        return True, 0.0, 0.0, ""
    soma = round(sum(c.componente.custo * c.quantidade for c in comps), 2)
    alvo = round(produto.custo, 2)
    if not alvo:
        return True, soma, 0.0, ""
    dif = round(soma - alvo, 2)
    if abs(dif) < 0.01:
        return True, soma, dif, "Soma dos componentes bate com o custo do kit."
    if dif < 0:
        return False, soma, dif, f"Faltam R$ {-dif:.2f} — esqueceu algum item?"
    return False, soma, dif, f"Passou R$ {dif:.2f} — quantidade a mais, ou custo desatualizado?"


def validar_componente(kit: Produto, componente: Produto) -> None:
    """Regras invioláveis da §5.2.5."""
    if componente.id == kit.id:
        raise ErroComposicao("Um kit não pode conter ele mesmo.")
    if componente.eh_kit:
        raise ErroComposicao(
            f"{componente.rotulo} também é um kit. Kit dentro de kit não é permitido — "
            "adicione os itens que compõem esse kit diretamente."
        )
    if not componente.ativo:
        raise ErroComposicao(f"{componente.rotulo} está inativo.")


def definir_composicao(
    session: Session, kit: Produto, itens: dict[int, int], *, validar: bool = True
) -> None:
    """Substitui a composição do kit. `itens` = {produto_id_componente: quantidade}.

    Não mexe em movimentos passados — eles registram o que saiu de fato (§5.2.5).
    """
    if not itens:
        raise ErroComposicao(
            "Um kit precisa de pelo menos um item. "
            "Se este produto não é montado com outros, transforme-o de volta em item simples."
        )

    if validar:
        for pid, qtd in itens.items():
            comp = session.get(Produto, pid)
            if comp is None:
                raise ErroComposicao(f"Item {pid} não existe.")
            if qtd < 1:
                raise ErroComposicao(f"A quantidade de {comp.rotulo} precisa ser 1 ou mais.")
            validar_componente(kit, comp)

    for antiga in componentes_de(session, kit):
        session.delete(antiga)
    session.flush()

    for pid, qtd in itens.items():
        session.add(Composicao(kit_id=kit.id, componente_id=pid, quantidade=qtd))
    kit.tipo = TipoProduto.KIT
    session.flush()
    session.expire(kit, ["componentes"])


def pode_virar_kit(session: Session, produto: Produto) -> tuple[bool, str]:
    """Checagem antes de transformar em kit (§5.2.1). Devolve (pode, motivo)."""
    if produto.eh_kit:
        return False, "Este produto já é um kit."
    usos = kits_afetados(session, produto)
    if usos:
        nomes = ", ".join(k.rotulo for k in usos[:3])
        resto = f" e mais {len(usos) - 3}" if len(usos) > 3 else ""
        return False, (
            f"{produto.rotulo} faz parte de {nomes}{resto}. "
            "Remova-o dessas composições antes de transformá-lo em kit."
        )
    return True, ""


def kits_sem_composicao(session: Session) -> list[Produto]:
    """Alimenta a tela 'Kits sem composição' (§5.2.1)."""
    kits = session.scalars(
        select(Produto).where(Produto.tipo == TipoProduto.KIT, Produto.ativo.is_(True))
    ).all()
    return [k for k in kits if not componentes_de(session, k)]
