"""Tirar um produto do catálogo — ESCOPO.md §5.2.6.

São DUAS operações, e a diferença não é detalhe técnico: é a garantia de que o
histórico nunca mente.

    ARQUIVAR — o produto some das listas, os movimentos continuam lá.
               Sempre reversível (`reativar`).
    EXCLUIR  — apaga a linha do banco. Só é permitido quando NADA aponta para
               ela: nenhum movimento, nenhuma composição de kit.

Movimento nunca é apagado junto com produto. Apagar quebraria o invariante do
§4.1 (estoque é a soma dos movimentos) e faria o histórico de uma venda antiga
perder o item que saiu. Quando existe histórico, a resposta certa é arquivar.

`analisar()` decide qual das duas cabe e já devolve o texto que a tela mostra —
a interface não repete regra de negócio.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .kits import componentes_de, kits_afetados
from .models import Composicao, Movimento, Produto, Saldo, VendaItem, VinculoML


class ErroExclusao(Exception):
    """Exclusão recusada. A mensagem vai para a tela como está."""


@dataclass
class Analise:
    """O que acontece se este produto sair — tudo que a tela precisa perguntar."""

    produto: Produto
    movimentos: int = 0
    vendas: int = 0
    saldo: int = 0
    kits_que_usam: list[Produto] = field(default_factory=list)
    componentes: int = 0

    @property
    def registros(self) -> int:
        """Histórico total: baixas de estoque + linhas de dinheiro.

        São duas tabelas por motivos diferentes (§4.4), mas para quem usa é uma
        coisa só — "este produto já teve movimento". E `venda_item` guarda linha
        de venda CANCELADA, que não gera movimento nenhum: contar só `movimento`
        deixaria passar um produto que o banco recusa apagar.
        """
        return self.movimentos + self.vendas

    @property
    def bloqueado(self) -> bool:
        """Item que outros kits usam não sai — nem arquivado (§5.2.5)."""
        return bool(self.kits_que_usam)

    @property
    def pode_excluir(self) -> bool:
        """Apagar de vez só quando não há histórico nem kit dependendo dele."""
        return not self.bloqueado and self.registros == 0

    @property
    def motivo_bloqueio(self) -> str:
        if not self.bloqueado:
            return ""
        # "(arquivado)" evita o beco sem saída de mandar procurar um kit que
        # sumiu das listas — ele só aparece no filtro Arquivados.
        nomes = ", ".join(
            k.rotulo + ("" if k.ativo else " (arquivado)")
            for k in self.kits_que_usam[:3]
        )
        resto = (
            f" e mais {len(self.kits_que_usam) - 3}"
            if len(self.kits_que_usam) > 3
            else ""
        )
        return (
            f"{self.produto.rotulo} faz parte de {nomes}{resto}. "
            "Esses kits parariam de saber de que são montados.\n\n"
            "Remova-o dessas composições primeiro — depois dá para excluir."
        )

    @property
    def resumo(self) -> str:
        """A frase da confirmação, já com os números (§6: sempre com número)."""
        if self.pode_excluir:
            texto = (
                f"{self.produto.rotulo} nunca foi movimentado — "
                "nenhuma venda, entrada ou ajuste.\n\n"
                "Vou apagar de vez. Isso não tem como desfazer."
            )
            if self.componentes:
                texto += (
                    f"\n\nA composição deste kit ({self.componentes} "
                    f"{'item' if self.componentes == 1 else 'itens'}) sai junto. "
                    "Os itens em si continuam no estoque."
                )
            return texto

        texto = (
            f"{self.produto.rotulo} tem {self.registros} "
            f"{'registro' if self.registros == 1 else 'registros'} no histórico, "
            "e histórico não se apaga.\n\n"
            "Vou arquivar: ele some das listas e das buscas, mas as vendas "
            "antigas continuam certas. Dá para trazer de volta depois."
        )
        if self.saldo:
            texto += f"\n\nAtenção: ainda constam {self.saldo} em estoque."
        return texto


def analisar(session: Session, produto: Produto) -> Analise:
    """Levanta tudo que aponta para o produto. Não altera nada."""
    movimentos = int(
        session.scalar(
            select(func.count())
            .select_from(Movimento)
            .where(
                or_(
                    Movimento.produto_id == produto.id,
                    Movimento.produto_vendido_id == produto.id,
                )
            )
        )
        or 0
    )
    vendas = int(
        session.scalar(
            select(func.count())
            .select_from(VendaItem)
            .where(VendaItem.produto_id == produto.id)
        )
        or 0
    )
    saldo = 0
    if not produto.eh_kit:
        from .ledger import saldo_de

        saldo = saldo_de(session, produto)

    return Analise(
        produto=produto,
        movimentos=movimentos,
        vendas=vendas,
        saldo=saldo,
        kits_que_usam=kits_afetados(session, produto),
        componentes=len(componentes_de(session, produto)) if produto.eh_kit else 0,
    )


def excluir(session: Session, produto: Produto) -> str:
    """Apaga o produto de vez. Devolve o rótulo — depois do delete ele some.

    Levanta `ErroExclusao` quando há histórico ou kit dependendo dele. As mesmas
    regras estão nas chaves estrangeiras do banco; aqui elas viram frase em
    português antes de o SQLite recusar com um erro que ninguém entende.
    """
    a = analisar(session, produto)
    if a.bloqueado:
        raise ErroExclusao(a.motivo_bloqueio)
    if a.registros:
        raise ErroExclusao(
            f"{produto.rotulo} tem {a.registros} registros no histórico e não "
            "pode ser apagado. Arquive-o: ele some das listas e o histórico fica."
        )

    rotulo = produto.rotulo
    session.execute(delete(Composicao).where(Composicao.kit_id == produto.id))
    session.execute(delete(Saldo).where(Saldo.produto_id == produto.id))
    session.execute(delete(VinculoML).where(VinculoML.produto_id == produto.id))
    session.flush()
    # A sessão usa expire_on_commit=False, então `componentes` e `saldos` podem
    # estar obsoletos em memória. Sem expirar, o cascade do ORM tentaria apagar
    # linhas que já saíram — mesma classe de bug que `componentes_de` evita.
    session.expire(produto)
    session.delete(produto)
    session.flush()
    return rotulo


def arquivar(session: Session, produto: Produto) -> None:
    """Tira das listas sem tocar no histórico. Reversível por `reativar`."""
    a = analisar(session, produto)
    if a.bloqueado:
        raise ErroExclusao(a.motivo_bloqueio)
    produto.ativo = False
    session.flush()


def reativar(session: Session, produto: Produto) -> None:
    produto.ativo = True
    session.flush()


def arquivados(session: Session, texto: str = "") -> list[Produto]:
    """Alimenta o filtro 'Arquivados' da tela de estoque."""
    from .repo import buscar

    return [p for p in buscar(session, texto, apenas_ativos=False) if not p.ativo]
