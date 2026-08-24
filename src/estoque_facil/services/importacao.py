"""Importação em duas fases — ESCOPO.md §5.1.

  analisar()  → não grava nada. Devolve as linhas classificadas para conferência.
  confirmar() → grava TUDO numa transação só. Ou entra tudo, ou nada.

É a tela de conferência entre as duas que impede baixa errada, e é por isso que
a análise não toca no banco.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import ledger, repo
from ..core.kits import ErroComposicao, custo_montado, disponivel, explodir
from ..core.models import (
    FULL,
    LoteImportacao,
    Movimento,
    OrigemMovimento,
    Produto,
    StatusLote,
    TipoMovimento,
    TipoProduto,
    VendaItem,
    normalizar_sku,
)
from ..importers import catalogo_csv, ml_vendas_xlsx
from ..importers.ml_vendas_xlsx import LinhaVenda, RelatorioML


class Situacao(StrEnum):
    PRONTA = "pronta"                 # verde
    ATENCAO = "atencao"               # amarelo
    SEM_CADASTRO = "sem_cadastro"     # vermelho
    JA_PROCESSADA = "ja_processada"   # branco
    NAO_ABATE = "nao_abate"           # cancelada/não concretizada


@dataclass
class LinhaAnalise:
    origem: LinhaVenda
    situacao: Situacao
    produto: Produto | None = None
    motivo: str = ""
    baixas: list[tuple[Produto, int]] = field(default_factory=list)

    @property
    def sku(self) -> str:
        return self.origem.sku or self.origem.mlb

    @property
    def descricao(self) -> str:
        if self.produto:
            return self.produto.rotulo
        return self.origem.titulo or self.sku


@dataclass
class AnaliseVendas:
    relatorio: RelatorioML
    linhas: list[LinhaAnalise]
    arquivo: Path
    hash_arquivo: str

    def por(self, situacao: Situacao) -> list[LinhaAnalise]:
        return [ln for ln in self.linhas if ln.situacao == situacao]

    @property
    def aplicaveis(self) -> list[LinhaAnalise]:
        return [ln for ln in self.linhas if ln.situacao in (Situacao.PRONTA, Situacao.ATENCAO)]

    @property
    def unidades_a_baixar(self) -> int:
        return sum(q for ln in self.aplicaveis for _, q in ln.baixas)

    @property
    def produtos_afetados(self) -> int:
        return len({p.id for ln in self.aplicaveis for p, _ in ln.baixas})

    def resumo(self) -> str:
        """A frase do topo da tela de conferência (§5.1 passo 5)."""
        n = len(self.aplicaveis)
        if not n:
            return "Nenhuma venda nova neste arquivo."
        partes = [
            f"{n} venda{'s' if n > 1 else ''} nova{'s' if n > 1 else ''} → "
            f"{self.unidades_a_baixar} unidades a baixar em {self.produtos_afetados} produtos"
        ]
        sem = len(self.por(Situacao.SEM_CADASTRO))
        if sem:
            partes.append(
                f"{sem} linhas precisam de atenção" if sem > 1
                else "1 linha precisa de atenção"
            )
        return ". ".join(partes) + "."


def _hash(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _ja_processadas(session: Session) -> set[str]:
    """Dedupe por N.º de venda, não por arquivo (§2.3) — relatórios se sobrepõem."""
    refs = session.scalars(
        select(Movimento.referencia_externa).where(
            Movimento.origem == OrigemMovimento.IMPORTACAO_ML,
            Movimento.tipo == TipoMovimento.VENDA,
            Movimento.referencia_externa.isnot(None),
        )
    ).all()
    return {r for r in refs if r}


def _casar(session: Session, linha: LinhaVenda) -> Produto | None:
    """Cascata de casamento da §2.4."""
    if linha.sku:
        p = repo.por_sku(session, linha.sku)
        if p:
            return p
    if linha.mlb:
        p = repo.por_ml(session, linha.mlb, linha.variacao)
        if p:
            return p
        p = repo.por_vinculo(session, f"{linha.mlb}|{linha.variacao}".lower())
        if p:
            return p
    if linha.sku:
        return repo.por_vinculo(session, linha.sku)
    return None


def analisar_vendas(session: Session, caminho: str | Path) -> AnaliseVendas:
    caminho = Path(caminho)
    relatorio = ml_vendas_xlsx.ler(caminho)
    processadas = _ja_processadas(session)
    linhas: list[LinhaAnalise] = []

    for lv in relatorio.linhas:
        if lv.numero_venda in processadas:
            linhas.append(LinhaAnalise(lv, Situacao.JA_PROCESSADA,
                                       motivo="Já importada antes."))
            continue

        if not lv.abate:
            motivo = (
                "Venda cancelada." if lv.cancelada
                else f"Status “{lv.estado}” não baixa estoque."
            )
            linhas.append(LinhaAnalise(lv, Situacao.NAO_ABATE, motivo=motivo))
            continue

        produto = _casar(session, lv)
        if produto is None:
            linhas.append(
                LinhaAnalise(
                    lv,
                    Situacao.SEM_CADASTRO,
                    motivo=f"Não achei nenhum produto com o código “{lv.sku or lv.mlb}”.",
                )
            )
            continue

        try:
            itens = explodir(session, produto, lv.quantidade)
        except ErroComposicao as exc:
            linhas.append(LinhaAnalise(lv, Situacao.SEM_CADASTRO, produto=produto,
                                       motivo=str(exc)))
            continue

        baixas = [(i.produto, i.quantidade) for i in itens]
        avisos = []

        if lv.local == FULL:
            avisos.append("Saiu do estoque Full — não desconta do estoque de casa.")
        if lv.status_desconhecido:
            avisos.append(f"Status “{lv.estado}” é novo — confira se deve mesmo baixar.")
        if not produto.ativo:
            # A baixa acontece do mesmo jeito — a venda é real. Mas sem este aviso
            # o estoque mexeria num produto que sumiu de todas as telas.
            avisos.append(
                f"{produto.rotulo} está arquivado e mesmo assim vendeu. "
                "Traga-o de volta em Estoque → Arquivados se voltou à ativa."
            )
        for prod, qtd in baixas:
            atual = disponivel(session, prod).quantidade
            if atual - qtd < 0:
                avisos.append(f"{prod.rotulo} ficará negativo ({atual} − {qtd}).")

        situacao = Situacao.ATENCAO if avisos else Situacao.PRONTA
        linhas.append(
            LinhaAnalise(lv, situacao, produto=produto, baixas=baixas, motivo=" ".join(avisos))
        )

    return AnaliseVendas(
        relatorio=relatorio, linhas=linhas, arquivo=caminho, hash_arquivo=_hash(caminho)
    )


@dataclass
class ResumoImportacao:
    lote_id: int
    movimentos: int
    vendas_aplicadas: int
    ignoradas: int
    pendentes: int
    linhas_financeiras: int = 0     # linhas novas gravadas para o balanço
    linhas_corrigidas: int = 0      # linhas que já existiam e mudaram de valor


def _chave_financeira(lv: LinhaVenda) -> str:
    """Identifica a linha dentro da venda. Uma venda pode ter vários produtos."""
    return normalizar_sku(lv.sku or lv.mlb or lv.titulo)[:200]


def _gravar_financeiro(session: Session, linha: LinhaAnalise, lote_id: int) -> str:
    """Guarda o DINHEIRO da linha — o estoque já foi tratado em outro lugar.

    Grava TODAS as linhas do relatório, inclusive canceladas e sem cadastro:
    receita cancelada some do balanço pelos próprios números do ML, e receita de
    produto não cadastrado existe de verdade — escondê-la daria um lucro errado.

    Quando a linha já existe, ATUALIZA em vez de ignorar. Relatórios se sobrepõem
    (§2.3): a venda de ontem que aparecia como "pronta para enviar" pode voltar
    hoje cancelada ou com devolução, e o balanço precisa do número mais recente.
    """
    lv = linha.origem
    produto = linha.produto
    chave = _chave_financeira(lv)
    if not lv.numero_venda or not chave:
        return "ignorado"

    item = session.scalar(
        select(VendaItem).where(
            VendaItem.numero_venda == lv.numero_venda, VendaItem.sku_ref == chave
        )
    )
    novo = item is None
    if novo:
        item = VendaItem(numero_venda=lv.numero_venda, sku_ref=chave, lote_id=lote_id)
        session.add(item)

    antes = (item.total_liquido, item.quantidade, item.devolvidas)

    item.produto_id = produto.id if produto else item.produto_id
    item.titulo = lv.titulo or (produto.rotulo if produto else "")
    item.quantidade = lv.quantidade
    item.devolvidas = lv.devolvidas
    item.abateu_estoque = bool(linha.baixas)
    item.cancelada = lv.cancelada or not lv.abate
    item.local_codigo = lv.local
    item.preco_unitario = lv.preco_unitario
    item.receita_produtos = lv.receita_produtos
    item.receita_envio = lv.receita_envio
    item.tarifa_venda = lv.tarifa_venda
    item.tarifa_envio = lv.tarifa_envio
    item.descontos = lv.descontos
    item.cancelamentos = lv.cancelamentos
    item.total_liquido = lv.total
    item.data_venda = lv.data

    # Fotografia do custo: só na criação. Reimportar um relatório antigo não pode
    # reescrever o custo de uma venda com o preço de compra de hoje.
    if novo and produto is not None:
        item.custo_unitario = custo_montado(session, produto)
        item.imposto_unitario = round(produto.imposto or 0.0, 4)

    session.flush()
    if novo:
        return "novo"
    return "atualizado" if antes != (item.total_liquido, item.quantidade, item.devolvidas) \
        else "igual"


def confirmar_vendas(session: Session, analise: AnaliseVendas) -> ResumoImportacao:
    """Grava tudo numa transação. Quem chama controla o commit (§5.1 passo 7)."""
    rel = analise.relatorio
    lote = LoteImportacao(
        arquivo_nome=rel.arquivo,
        arquivo_hash=analise.hash_arquivo,
        tipo="vendas_ml",
        periodo_inicio=rel.periodo_inicio,
        periodo_fim=rel.periodo_fim,
        linhas_total=len(rel.linhas),
        linhas_novas=len(analise.aplicaveis),
        linhas_ignoradas=len(analise.por(Situacao.JA_PROCESSADA)),
        linhas_pendentes=len(analise.por(Situacao.SEM_CADASTRO)),
        status=StatusLote.CONFIRMADO,
    )
    session.add(lote)
    session.flush()

    total_mov = aplicadas = ignoradas = 0
    for linha in analise.aplicaveis:
        assert linha.produto is not None
        res = ledger.aplicar_venda(
            session,
            linha.produto,
            linha.origem.quantidade,
            referencia_externa=linha.origem.numero_venda,
            local_codigo=linha.origem.local,
            lote_id=lote.id,
            data_evento=linha.origem.data,
        )
        total_mov += len(res.movimentos)
        ignoradas += res.ignorados
        if res.movimentos:
            aplicadas += 1

    # Devoluções voltam ao estoque (§2.6)
    for linha in analise.linhas:
        lv = linha.origem
        if lv.devolvidas > 0 and linha.produto is not None:
            ledger.aplicar_devolucao(
                session, linha.produto, lv.devolvidas,
                referencia_externa=lv.numero_venda,
                local_codigo=lv.local, lote_id=lote.id, data_evento=lv.data,
            )

    # O dinheiro de TODAS as linhas, na mesma transação do estoque (§5.8)
    novas = corrigidas = 0
    for linha in analise.linhas:
        resultado = _gravar_financeiro(session, linha, lote.id)
        novas += resultado == "novo"
        corrigidas += resultado == "atualizado"

    from datetime import datetime

    lote.confirmado_em = datetime.now()
    session.flush()
    return ResumoImportacao(
        lote_id=lote.id,
        movimentos=total_mov,
        vendas_aplicadas=aplicadas,
        ignoradas=ignoradas,
        pendentes=len(analise.por(Situacao.SEM_CADASTRO)),
        linhas_financeiras=novas,
        linhas_corrigidas=corrigidas,
    )


# ---------------------------------------------------------------- carga inicial


@dataclass
class ResumoCatalogo:
    criados: int
    atualizados: int
    kits_marcados: int
    avisos: list[str]


def importar_catalogo(
    session: Session, caminho: str | Path, *, marcar_kits: bool = True,
    aplicar_estoque: bool = True,
) -> ResumoCatalogo:
    """Passo 1 da carga inicial (§5.3). Todos entram como simples, estoque zero."""
    cat = catalogo_csv.ler(caminho)
    criados = atualizados = kits = 0

    for linha in cat.linhas:
        produto = repo.por_sku(session, linha.sku)
        if produto is None:
            produto = repo.criar_produto(
                session, linha.sku, linha.nome, custo=linha.custo,
                imposto=linha.imposto, estoque_minimo=linha.minimo,
            )
            criados += 1
        else:
            produto.custo = linha.custo or produto.custo
            produto.imposto = linha.imposto or produto.imposto
            if linha.nome and not produto.nome:
                produto.nome = linha.nome
            if linha.minimo:
                produto.estoque_minimo = linha.minimo
            atualizados += 1

        if marcar_kits and linha.provavel_kit and produto.tipo != TipoProduto.KIT:
            produto.tipo = TipoProduto.KIT
            kits += 1

        if aplicar_estoque and linha.estoque is not None and produto.tipo == TipoProduto.SIMPLES:
            ledger.ajustar(
                session, produto, linha.estoque,
                tipo=TipoMovimento.INVENTARIO,
                observacao=f"Carga inicial ({cat.arquivo})",
            )

    session.flush()
    return ResumoCatalogo(criados, atualizados, kits, cat.avisos)


def preencher_nomes(session: Session, caminho: str | Path) -> int:
    """Passo 2 da carga inicial (§5.3): o relatório do ML dá nome aos SKUs."""
    relatorio = ml_vendas_xlsx.ler(caminho)
    preenchidos = 0
    for lv in relatorio.linhas:
        if not lv.sku or not lv.titulo:
            continue
        produto = repo.por_sku(session, lv.sku)
        if produto is None:
            continue
        mudou = False
        if not (produto.nome or "").strip():
            produto.nome = lv.titulo
            mudou = True
        if lv.mlb and not produto.ml_item_id:
            produto.ml_item_id = lv.mlb
            mudou = True
        if lv.variacao and not produto.variacao:
            produto.variacao = lv.variacao
            mudou = True
        if lv.preco_unitario and not produto.preco_venda:
            produto.preco_venda = lv.preco_unitario
            mudou = True
        if mudou:
            preenchidos += 1
    session.flush()
    return preenchidos


def produtos_do_relatorio(session: Session, caminho: str | Path) -> list[dict]:
    """SKUs do relatório que ainda não existem no catálogo (§2.8)."""
    relatorio = ml_vendas_xlsx.ler(caminho)
    novos: dict[str, dict] = {}
    for lv in relatorio.linhas:
        if not lv.sku or repo.por_sku(session, lv.sku):
            continue
        novos.setdefault(
            lv.sku.lower(),
            {
                "sku": lv.sku,
                "nome": lv.titulo,
                "ml_item_id": lv.mlb,
                "variacao": lv.variacao,
                "preco": lv.preco_unitario,
                "provavel_kit": catalogo_csv.parece_kit(lv.sku, lv.titulo),
            },
        )
    return list(novos.values())
