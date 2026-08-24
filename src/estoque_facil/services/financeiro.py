"""Balanço da loja: quanto entrou, quanto saiu, quanto sobrou — ESCOPO.md §5.8.

O balanço é uma CONTA, não uma tabela: nada aqui é gravado como saldo acumulado.
Ele é sempre recalculado a partir de três fontes independentes, pelo mesmo
motivo que o estoque é a soma dos movimentos — número guardado envelhece, conta
refeita não mente:

    vendas (VendaItem)  →  o que o Mercado Livre pagou, com as tarifas dele
    despesas (Despesa)  →  o que a loja gastou fora da mercadoria
    perdas (Movimento)  →  mercadoria que saiu sem vender

A ordem das linhas é a de um DRE simples, para que ela consiga conferir com o
extrato do ML de cima para baixo.
"""
from __future__ import annotations

import csv
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core import ledger
from ..core.models import (
    ROTULOS_DESPESA,
    CategoriaDespesa,
    Despesa,
    Produto,
    VendaItem,
)

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


class ErroFinanceiro(Exception):
    """Lançamento recusado. Mensagem já em português, pronta para a tela."""


# ------------------------------------------------------------------- períodos


def inicio_do_dia(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def fim_do_dia(d: datetime) -> datetime:
    return d.replace(hour=23, minute=59, second=59, microsecond=999999)


def mes(ano: int, numero: int) -> tuple[datetime, datetime]:
    ultimo = monthrange(ano, numero)[1]
    return (
        datetime(ano, numero, 1),
        fim_do_dia(datetime(ano, numero, ultimo)),
    )


def nome_do_mes(d: datetime) -> str:
    return f"{MESES_PT[d.month - 1]} de {d.year}"


def periodos(hoje: datetime | None = None) -> list[tuple[str, datetime, datetime]]:
    """Os atalhos da tela de balanço, em português."""
    hoje = hoje or datetime.now()
    este_inicio, este_fim = mes(hoje.year, hoje.month)
    anterior = este_inicio - timedelta(days=1)
    passado_inicio, passado_fim = mes(anterior.year, anterior.month)
    return [
        (f"Este mês ({MESES_PT[hoje.month - 1]})", este_inicio, este_fim),
        (f"Mês passado ({MESES_PT[anterior.month - 1]})", passado_inicio, passado_fim),
        ("Últimos 30 dias", inicio_do_dia(hoje - timedelta(days=29)), fim_do_dia(hoje)),
        ("Últimos 90 dias", inicio_do_dia(hoje - timedelta(days=89)), fim_do_dia(hoje)),
        (f"Este ano ({hoje.year})", datetime(hoje.year, 1, 1), fim_do_dia(hoje)),
    ]


# -------------------------------------------------------------------- despesas


def registrar_despesa(
    session: Session,
    descricao: str,
    valor: float,
    *,
    data: datetime | None = None,
    categoria: str = CategoriaDespesa.OUTROS,
    observacao: str | None = None,
) -> Despesa:
    """Lança um gasto. Descrição é obrigatória: 'R$ 300,00' sem o quê não serve."""
    descricao = (descricao or "").strip()
    if not descricao:
        raise ErroFinanceiro("Escreva o que foi essa despesa — só o valor não ajuda depois.")
    if valor is None or valor <= 0:
        raise ErroFinanceiro("O valor da despesa precisa ser maior que zero.")
    if categoria not in set(CategoriaDespesa):
        categoria = CategoriaDespesa.OUTROS

    despesa = Despesa(
        data=data or inicio_do_dia(datetime.now()),
        descricao=descricao,
        categoria=categoria,
        valor=round(float(valor), 2),
        observacao=(observacao or "").strip() or None,
    )
    session.add(despesa)
    session.flush()
    return despesa


def listar_despesas(
    session: Session, inicio: datetime | None = None, fim: datetime | None = None
) -> list[Despesa]:
    q = select(Despesa)
    if inicio:
        q = q.where(Despesa.data >= inicio)
    if fim:
        q = q.where(Despesa.data <= fim)
    return list(session.scalars(q.order_by(Despesa.data.desc(), Despesa.id.desc())).all())


def remover_despesa(session: Session, despesa_id: int) -> None:
    """Despesa é digitada à mão, então apagar é a correção certa — ao contrário
    de um movimento de estoque, que nunca some do histórico."""
    despesa = session.get(Despesa, despesa_id)
    if despesa is None:
        raise ErroFinanceiro("Essa despesa não existe mais.")
    session.delete(despesa)
    session.flush()


# --------------------------------------------------------------------- balanço


@dataclass
class LinhaProduto:
    produto: Produto | None
    titulo: str
    unidades: int
    receita: float          # o que sobrou do ML nesta linha
    custo: float
    imposto: float

    @property
    def lucro(self) -> float:
        return round(self.receita - self.custo - self.imposto, 2)

    @property
    def margem(self) -> float:
        return round(self.lucro / self.receita * 100, 1) if self.receita else 0.0


@dataclass
class Balanco:
    inicio: datetime
    fim: datetime

    receita_produtos: float = 0.0
    receita_envio: float = 0.0
    descontos: float = 0.0
    cancelamentos: float = 0.0
    tarifas_ml: float = 0.0          # negativo
    custos_envio: float = 0.0        # negativo
    recebido: float = 0.0            # o que o ML efetivamente pagou

    cmv: float = 0.0                 # custo da mercadoria vendida (positivo)
    impostos: float = 0.0            # imposto do cadastro, por unidade (positivo)
    perdas: float = 0.0              # mercadoria perdida, a custo (positivo)
    despesas: float = 0.0            # positivo

    vendas: int = 0
    unidades: int = 0
    devolvidas: int = 0
    linhas_sem_custo: int = 0
    despesas_por_categoria: dict[str, float] = field(default_factory=dict)

    @property
    def lucro(self) -> float:
        return round(
            self.recebido - self.cmv - self.impostos - self.perdas - self.despesas, 2
        )

    @property
    def margem(self) -> float:
        """Lucro sobre o que foi faturado em produtos."""
        base = self.receita_produtos
        return round(self.lucro / base * 100, 1) if base else 0.0

    @property
    def ticket_medio(self) -> float:
        return round(self.receita_produtos / self.vendas, 2) if self.vendas else 0.0

    @property
    def tem_dados(self) -> bool:
        return bool(self.vendas or self.despesas or self.perdas)

    @property
    def periodo_rotulo(self) -> str:
        return f"{self.inicio:%d/%m/%Y} a {self.fim:%d/%m/%Y}"

    def linhas(self) -> list[tuple[str, float, str]]:
        """As linhas do demonstrativo, na ordem em que ela lê (rótulo, valor, tipo).

        `tipo` é só para a tela pintar: entrada, saida, subtotal, resultado.
        """
        itens: list[tuple[str, float, str]] = [
            ("Vendas de produtos", self.receita_produtos, "entrada"),
            ("Frete cobrado do comprador", self.receita_envio, "entrada"),
            ("Descontos e bônus", self.descontos, "entrada" if self.descontos >= 0 else "saida"),
            ("Cancelamentos e reembolsos", self.cancelamentos, "saida"),
            ("Tarifas do Mercado Livre", self.tarifas_ml, "saida"),
            ("Custos de envio", self.custos_envio, "saida"),
            ("= Recebido do Mercado Livre", self.recebido, "subtotal"),
            ("Custo dos produtos vendidos", -self.cmv, "saida"),
            ("Impostos sobre as vendas", -self.impostos, "saida"),
            ("Perdas e quebras (a custo)", -self.perdas, "saida"),
            ("Despesas da loja", -self.despesas, "saida"),
            ("= Lucro do período", self.lucro, "resultado"),
        ]
        return itens


def _no_periodo(inicio: datetime, fim: datetime):
    """Data da venda quando existe; senão a data em que a linha foi importada."""
    quando = func.coalesce(VendaItem.data_venda, VendaItem.criado_em)
    return (quando >= inicio, quando <= fim)


def vendas_do_periodo(session: Session, inicio: datetime, fim: datetime) -> list[VendaItem]:
    return list(
        session.scalars(
            select(VendaItem)
            .where(*_no_periodo(inicio, fim))
            .order_by(func.coalesce(VendaItem.data_venda, VendaItem.criado_em).desc())
        ).all()
    )


def apurar(session: Session, inicio: datetime, fim: datetime) -> Balanco:
    """A conta inteira do período. Recalculada sempre, nunca guardada."""
    b = Balanco(inicio=inicio, fim=fim)

    vendas_por_numero: set[str] = set()
    for item in vendas_do_periodo(session, inicio, fim):
        b.receita_produtos += item.receita_produtos
        b.receita_envio += item.receita_envio
        b.descontos += item.descontos
        b.cancelamentos += item.cancelamentos
        b.tarifas_ml += item.tarifa_venda
        b.custos_envio += item.tarifa_envio
        b.recebido += item.total_liquido
        b.cmv += item.custo_total
        b.impostos += item.imposto_total
        b.unidades += item.quantidade_faturada
        b.devolvidas += item.devolvidas
        if item.sem_custo:
            b.linhas_sem_custo += 1
        vendas_por_numero.add(item.numero_venda)
    b.vendas = len(vendas_por_numero)

    b.perdas = round(sum(valor for _m, valor in ledger.perdas_do_periodo(session, inicio, fim)), 2)

    for despesa in listar_despesas(session, inicio, fim):
        b.despesas += despesa.valor
        rotulo = ROTULOS_DESPESA.get(despesa.categoria, "Outros")
        b.despesas_por_categoria[rotulo] = round(
            b.despesas_por_categoria.get(rotulo, 0.0) + despesa.valor, 2
        )

    for campo in (
        "receita_produtos", "receita_envio", "descontos", "cancelamentos",
        "tarifas_ml", "custos_envio", "recebido", "cmv", "impostos", "despesas",
    ):
        setattr(b, campo, round(getattr(b, campo), 2))
    return b


def por_produto(
    session: Session, inicio: datetime, fim: datetime, limite: int | None = None
) -> list[LinhaProduto]:
    """Quem deu lucro e quem deu prejuízo no período. Ordenado pelo lucro."""
    agrupado: dict[tuple[int | None, str], LinhaProduto] = {}
    for item in vendas_do_periodo(session, inicio, fim):
        titulo = item.titulo or item.sku_ref
        if item.produto is not None:
            titulo = item.produto.rotulo
        chave = (item.produto_id, titulo)
        linha = agrupado.get(chave)
        if linha is None:
            linha = LinhaProduto(item.produto, titulo, 0, 0.0, 0.0, 0.0)
            agrupado[chave] = linha
        linha.unidades += item.quantidade_faturada
        linha.receita = round(linha.receita + item.total_liquido, 2)
        linha.custo = round(linha.custo + item.custo_total, 2)
        linha.imposto = round(linha.imposto + item.imposto_total, 2)

    linhas = sorted(agrupado.values(), key=lambda ln: ln.lucro, reverse=True)
    return linhas[:limite] if limite else linhas


def exportar_csv(session: Session, balanco: Balanco, destino: Path | str) -> Path:
    """Planilha do período — o que ela manda para o contador."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Balanço do período", balanco.periodo_rotulo])
        w.writerow([])
        w.writerow(["Linha", "Valor (R$)"])
        for rotulo, valor, _tipo in balanco.linhas():
            w.writerow([rotulo, f"{valor:.2f}".replace(".", ",")])

        w.writerow([])
        w.writerow(["Despesas do período"])
        w.writerow(["Data", "Categoria", "Descrição", "Valor (R$)"])
        for despesa in listar_despesas(session, balanco.inicio, balanco.fim):
            w.writerow([
                f"{despesa.data:%d/%m/%Y}",
                despesa.categoria_rotulo,
                despesa.descricao,
                f"{despesa.valor:.2f}".replace(".", ","),
            ])

        w.writerow([])
        w.writerow(["Produto", "Unidades", "Recebido", "Custo", "Imposto", "Lucro", "Margem %"])
        for linha in por_produto(session, balanco.inicio, balanco.fim):
            w.writerow([
                linha.titulo, linha.unidades,
                f"{linha.receita:.2f}".replace(".", ","),
                f"{linha.custo:.2f}".replace(".", ","),
                f"{linha.imposto:.2f}".replace(".", ","),
                f"{linha.lucro:.2f}".replace(".", ","),
                f"{linha.margem:.1f}".replace(".", ","),
            ])
    return destino


def resumo_do_mes(session: Session, hoje: datetime | None = None) -> Balanco:
    """Atalho para a faixa da tela inicial."""
    hoje = hoje or datetime.now()
    inicio, fim = mes(hoje.year, hoje.month)
    return apurar(session, inicio, fim)
