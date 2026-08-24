"""Acesso a dados. Nenhuma regra de negócio aqui — só busca e criação."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .kits import disponivel
from .models import Produto, TipoProduto, VinculoML, normalizar_sku


def por_sku(session: Session, sku: str) -> Produto | None:
    return session.scalar(select(Produto).where(Produto.sku_norm == normalizar_sku(sku)))


def por_ml(session: Session, ml_item_id: str, variacao: str | None = None) -> Produto | None:
    q = select(Produto).where(Produto.ml_item_id == ml_item_id)
    if variacao:
        alvo = session.scalar(q.where(Produto.variacao == variacao))
        if alvo:
            return alvo
    return session.scalar(q)


def por_vinculo(session: Session, chave: str) -> Produto | None:
    v = session.scalar(select(VinculoML).where(VinculoML.chave == chave.strip().lower()))
    return v.produto if v else None


def criar_vinculo(session: Session, chave: str, produto: Produto) -> VinculoML:
    chave = chave.strip().lower()
    v = session.scalar(select(VinculoML).where(VinculoML.chave == chave))
    if v:
        v.produto_id = produto.id
    else:
        v = VinculoML(chave=chave, produto_id=produto.id)
        session.add(v)
    session.flush()
    return v


def criar_produto(
    session: Session,
    sku: str,
    nome: str = "",
    *,
    tipo: str = TipoProduto.SIMPLES,
    custo: float = 0.0,
    imposto: float = 0.0,
    ml_item_id: str | None = None,
    variacao: str | None = None,
    estoque_minimo: int = 0,
) -> Produto:
    sku = (sku or "").strip()
    if not sku:
        raise ValueError("O código do produto (SKU) não pode ficar vazio.")
    existente = por_sku(session, sku)
    if existente:
        raise ValueError(f"Já existe um produto com o código {existente.sku}.")
    p = Produto(
        sku=sku,
        sku_norm=normalizar_sku(sku),
        nome=nome or "",
        tipo=tipo,
        custo=custo,
        imposto=imposto,
        ml_item_id=ml_item_id,
        variacao=variacao,
        estoque_minimo=estoque_minimo,
    )
    session.add(p)
    session.flush()
    return p


def buscar(
    session: Session, texto: str = "", *, tipo: str | None = None, apenas_ativos: bool = True
) -> list[Produto]:
    """Busca única: nome, código e código de barras ao mesmo tempo (§6)."""
    q = select(Produto)
    if apenas_ativos:
        q = q.where(Produto.ativo.is_(True))
    if tipo:
        q = q.where(Produto.tipo == tipo)
    texto = (texto or "").strip()
    if texto:
        alvo = f"%{texto.lower()}%"
        q = q.where(
            or_(
                func.lower(Produto.nome).like(alvo),
                Produto.sku_norm.like(alvo),
                func.lower(func.coalesce(Produto.codigo_barras, "")).like(alvo),
            )
        )
    return list(session.scalars(q.order_by(Produto.tipo, Produto.sku)).all())


def contar(session: Session) -> dict[str, int]:
    """Só o catálogo vivo. Arquivado não entra em contador nem em alerta."""
    total = (
        session.scalar(
            select(func.count()).select_from(Produto).where(Produto.ativo.is_(True))
        )
        or 0
    )
    kits = (
        session.scalar(
            select(func.count())
            .select_from(Produto)
            .where(Produto.ativo.is_(True), Produto.tipo == TipoProduto.KIT)
        )
        or 0
    )
    return {"total": int(total), "kits": int(kits), "simples": int(total) - int(kits)}


def abaixo_do_minimo(session: Session) -> list[tuple[Produto, int, list[Produto]]]:
    """Produtos em alerta, com os kits que cada um trava (§5.2.4)."""
    from .kits import kits_afetados

    saida = []
    produtos = session.scalars(
        select(Produto).where(
            Produto.ativo.is_(True),
            Produto.tipo == TipoProduto.SIMPLES,
            Produto.estoque_minimo > 0,
        )
    ).all()
    for p in produtos:
        d = disponivel(session, p)
        if d.quantidade <= p.estoque_minimo:
            saida.append((p, d.quantidade, kits_afetados(session, p)))
    saida.sort(key=lambda t: (t[1] - 0, -len(t[2])))
    return saida
