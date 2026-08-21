"""Livro-razão — ESCOPO.md §4.1.

Estoque é a SOMA DOS MOVIMENTOS. `Saldo` é cache, e `recalcular_saldos()` prova isso
a qualquer momento. Todo caminho de escrita passa por `registrar()` — não existe
outro lugar no código que mexa em `Saldo`.

Decisão de implementação (desvio consciente do texto do escopo, §4.1):
`desfazer_lote()` APAGA os movimentos daquele lote em vez de gerar estornos.
Motivo: com estorno, os movimentos originais continuariam existindo e a
deduplicação por N.º de venda impediria a reimportação do arquivo corrigido —
exatamente o que a usuária tentaria fazer depois de desfazer. A trilha de
auditoria fica no `LoteImportacao`, que guarda os números e o status DESFEITO.
Correções pontuais continuam sendo novos movimentos de ajuste, nunca edição.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import local_id
from .kits import explodir
from .models import (
    CASA,
    LoteImportacao,
    Movimento,
    OrigemMovimento,
    Produto,
    Saldo,
    StatusLote,
    TipoMovimento,
)


class ErroEstoque(Exception):
    """Operação recusada. Mensagem já em português, pronta para a tela."""


@dataclass
class ResultadoBaixa:
    movimentos: list[Movimento]
    ignorados: int = 0          # já processados antes (idempotência)


def _saldo_row(session: Session, produto_id: int, lid: int) -> Saldo:
    s = session.scalar(
        select(Saldo).where(Saldo.produto_id == produto_id, Saldo.local_id == lid)
    )
    if s is None:
        s = Saldo(produto_id=produto_id, local_id=lid, quantidade=0)
        session.add(s)
        session.flush()
    return s


def registrar(
    session: Session,
    produto: Produto,
    quantidade: int,
    tipo: str,
    *,
    local_codigo: str = CASA,
    origem: str = OrigemMovimento.MANUAL,
    referencia_externa: str | None = None,
    produto_vendido: Produto | None = None,
    lote_id: int | None = None,
    observacao: str | None = None,
    data_evento: datetime | None = None,
) -> Movimento | None:
    """Grava UM movimento e atualiza o cache. `quantidade` com sinal: + entra, - sai.

    Devolve None quando o movimento já existia (idempotência garantida pelo índice
    único do banco — ESCOPO.md §4.3). Nunca levanta erro por duplicata.
    """
    if produto.eh_kit:
        raise ErroEstoque(
            f"{produto.rotulo} é um kit e não tem estoque próprio. "
            "O estoque vem dos itens que o compõem."
        )
    if quantidade == 0:
        raise ErroEstoque("Movimento de quantidade zero não faz sentido.")

    lid = local_id(session, local_codigo)
    saldo = _saldo_row(session, produto.id, lid)
    novo = saldo.quantidade + quantidade

    mov = Movimento(
        produto_id=produto.id,
        local_id=lid,
        tipo=tipo,
        quantidade=quantidade,
        saldo_apos=novo,
        origem=origem,
        referencia_externa=referencia_externa,
        produto_vendido_id=produto_vendido.id if produto_vendido else None,
        lote_id=lote_id,
        observacao=observacao,
        data_evento=data_evento,
    )
    # SAVEPOINT, não rollback: a duplicata precisa derrubar ESTA linha e só ela.
    # Com rollback simples, uma venda repetida no meio do arquivo desfazia toda a
    # importação anterior — e as linhas seguintes entravam como se fossem novas.
    try:
        with session.begin_nested():
            session.add(mov)
            session.flush()
    except IntegrityError:
        if mov in session:
            session.expunge(mov)
        return None

    saldo.quantidade = novo
    session.flush()
    return mov


def aplicar_venda(
    session: Session,
    produto: Produto,
    quantidade: int,
    *,
    referencia_externa: str,
    local_codigo: str = CASA,
    origem: str = OrigemMovimento.IMPORTACAO_ML,
    lote_id: int | None = None,
    data_evento: datetime | None = None,
    observacao: str | None = None,
) -> ResultadoBaixa:
    """Baixa uma venda. Kit vira N baixas de componentes (§5.1 passo 4)."""
    itens = explodir(session, produto, quantidade)
    movs, ignorados = [], 0
    for item in itens:
        m = registrar(
            session,
            item.produto,
            -item.quantidade,
            TipoMovimento.VENDA,
            local_codigo=local_codigo,
            origem=origem,
            referencia_externa=referencia_externa,
            produto_vendido=item.vendido_como,
            lote_id=lote_id,
            data_evento=data_evento,
            observacao=observacao,
        )
        if m is None:
            ignorados += 1
        else:
            movs.append(m)
    return ResultadoBaixa(movimentos=movs, ignorados=ignorados)


def aplicar_devolucao(
    session: Session,
    produto: Produto,
    quantidade: int,
    *,
    referencia_externa: str,
    local_codigo: str = CASA,
    lote_id: int | None = None,
    data_evento: datetime | None = None,
) -> ResultadoBaixa:
    """Devolução volta ao estoque. Kit volta como componentes (§2.6)."""
    itens = explodir(session, produto, quantidade)
    movs, ignorados = [], 0
    for item in itens:
        m = registrar(
            session,
            item.produto,
            item.quantidade,
            TipoMovimento.DEVOLUCAO,
            local_codigo=local_codigo,
            origem=OrigemMovimento.IMPORTACAO_ML,
            referencia_externa=f"{referencia_externa}:dev",
            produto_vendido=item.vendido_como,
            lote_id=lote_id,
            data_evento=data_evento,
        )
        if m is None:
            ignorados += 1
        else:
            movs.append(m)
    return ResultadoBaixa(movimentos=movs, ignorados=ignorados)


def entrada_compra(
    session: Session,
    produto: Produto,
    quantidade: int,
    custo_unitario: float | None = None,
    *,
    local_codigo: str = CASA,
    observacao: str | None = None,
) -> Movimento:
    """Compra de mercadoria. Atualiza o custo médio ponderado (§5.4)."""
    if quantidade <= 0:
        raise ErroEstoque("A quantidade de entrada precisa ser maior que zero.")

    if custo_unitario is not None and custo_unitario > 0:
        atual = saldo_de(session, produto, local_codigo)
        if atual > 0 and produto.custo > 0:
            total = produto.custo * atual + custo_unitario * quantidade
            produto.custo = round(total / (atual + quantidade), 4)
        else:
            produto.custo = round(custo_unitario, 4)

    mov = registrar(
        session, produto, quantidade, TipoMovimento.COMPRA,
        local_codigo=local_codigo, observacao=observacao,
    )
    assert mov is not None
    return mov


def ajustar(
    session: Session,
    produto: Produto,
    nova_quantidade: int,
    *,
    local_codigo: str = CASA,
    tipo: str = TipoMovimento.AJUSTE,
    observacao: str | None = None,
) -> Movimento | None:
    """Leva o saldo para um valor exato (contagem física, correção)."""
    atual = saldo_de(session, produto, local_codigo)
    delta = nova_quantidade - atual
    if delta == 0:
        return None
    return registrar(
        session, produto, delta, tipo, local_codigo=local_codigo,
        observacao=observacao or f"Ajuste de {atual} para {nova_quantidade}",
    )


def saldo_de(session: Session, produto: Produto, local_codigo: str = CASA) -> int:
    lid = local_id(session, local_codigo)
    s = session.scalar(
        select(Saldo).where(Saldo.produto_id == produto.id, Saldo.local_id == lid)
    )
    return s.quantidade if s else 0


def desfazer_lote(session: Session, lote_id: int) -> int:
    """Reverte uma importação inteira (§5.1 passo 8). Devolve quantos movimentos saíram."""
    lote = session.get(LoteImportacao, lote_id)
    if lote is None:
        raise ErroEstoque("Importação não encontrada.")
    if lote.status == StatusLote.DESFEITO:
        raise ErroEstoque("Esta importação já foi desfeita.")

    qtd = session.scalar(
        select(func.count()).select_from(Movimento).where(Movimento.lote_id == lote_id)
    )
    session.execute(delete(Movimento).where(Movimento.lote_id == lote_id))
    lote.status = StatusLote.DESFEITO
    session.flush()
    recalcular_saldos(session)
    return int(qtd or 0)


def recalcular_saldos(session: Session) -> dict[tuple[int, int], int]:
    """Reconstrói o cache a partir dos movimentos. É a prova do invariante (§11.1)."""
    somas = session.execute(
        select(Movimento.produto_id, Movimento.local_id, func.sum(Movimento.quantidade))
        .group_by(Movimento.produto_id, Movimento.local_id)
    ).all()
    esperado = {(p, lc): int(q or 0) for p, lc, q in somas}

    for saldo in session.scalars(select(Saldo)).all():
        saldo.quantidade = esperado.get((saldo.produto_id, saldo.local_id), 0)
    for (pid, lid), qtd in esperado.items():
        row = session.scalar(
            select(Saldo).where(Saldo.produto_id == pid, Saldo.local_id == lid)
        )
        if row is None:
            session.add(Saldo(produto_id=pid, local_id=lid, quantidade=qtd))
    session.flush()
    return esperado


def verificar_invariante(session: Session) -> list[str]:
    """Lista divergências entre o cache e o livro-razão. Vazio = tudo certo."""
    somas = session.execute(
        select(Movimento.produto_id, Movimento.local_id, func.sum(Movimento.quantidade))
        .group_by(Movimento.produto_id, Movimento.local_id)
    ).all()
    esperado = {(p, lc): int(q or 0) for p, lc, q in somas}
    problemas = []
    for saldo in session.scalars(select(Saldo)).all():
        alvo = esperado.get((saldo.produto_id, saldo.local_id), 0)
        if saldo.quantidade != alvo:
            prod = session.get(Produto, saldo.produto_id)
            nome = prod.rotulo if prod else saldo.produto_id
            problemas.append(f"{nome}: cache {saldo.quantidade}, movimentos somam {alvo}")
    return problemas


def historico(session: Session, produto: Produto, limite: int = 200) -> list[Movimento]:
    return list(
        session.scalars(
            select(Movimento)
            .where(Movimento.produto_id == produto.id)
            .order_by(Movimento.criado_em.desc(), Movimento.id.desc())
            .limit(limite)
        ).all()
    )


def descrever(mov: Movimento) -> str:
    """Linha de histórico em português, explicando kits (§4.3)."""
    rotulos = {
        TipoMovimento.VENDA: "Venda",
        TipoMovimento.DEVOLUCAO: "Devolução",
        TipoMovimento.COMPRA: "Entrada de mercadoria",
        TipoMovimento.AJUSTE: "Ajuste",
        TipoMovimento.INVENTARIO: "Contagem física",
        TipoMovimento.DESMONTAGEM: "Desmontagem de kit",
        TipoMovimento.TRANSFERENCIA_SAIDA: "Enviado para o Full",
        TipoMovimento.TRANSFERENCIA_ENTRADA: "Recebido do Full",
        TipoMovimento.CANCELAMENTO: "Cancelamento",
    }
    txt = rotulos.get(mov.tipo, mov.tipo)
    if mov.produto_vendido is not None and mov.produto_vendido_id != mov.produto_id:
        txt += f" — saiu por {mov.produto_vendido.rotulo}"
    if mov.referencia_externa:
        txt += f" (venda {mov.referencia_externa})"
    return txt
