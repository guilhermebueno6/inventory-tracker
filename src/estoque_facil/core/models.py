"""Modelo de dados — ESCOPO.md §4.

Dois princípios que o resto do código depende:

1. Estoque é a SOMA DOS MOVIMENTOS. `Saldo` é só cache, sempre recalculável.
   Movimentos nunca são editados nem apagados; correção é novo movimento.

2. KIT NÃO TEM SALDO. O que existe na prateleira são os componentes.
   `disponivel(kit) = min(saldo(componente) // quantidade)`.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TipoProduto(enum.StrEnum):
    SIMPLES = "simples"
    KIT = "kit"


class TipoMovimento(enum.StrEnum):
    VENDA = "venda"
    DEVOLUCAO = "devolucao"
    COMPRA = "compra"
    AJUSTE = "ajuste"
    INVENTARIO = "inventario"
    TRANSFERENCIA_SAIDA = "transferencia_saida"
    TRANSFERENCIA_ENTRADA = "transferencia_entrada"
    CANCELAMENTO = "cancelamento"
    DESMONTAGEM = "desmontagem"


class OrigemMovimento(enum.StrEnum):
    MANUAL = "manual"
    IMPORTACAO_ML = "importacao_ml"
    IMPORTACAO_PLANILHA = "importacao_planilha"
    API_ML = "api_ml"


class StatusLote(enum.StrEnum):
    RASCUNHO = "rascunho"
    CONFIRMADO = "confirmado"
    DESFEITO = "desfeito"


CASA = "CASA"
FULL = "FULL"


def _agora() -> datetime:
    return datetime.now()


def normalizar_sku(sku: str) -> str:
    """O ML mistura KIT.MAOPE.ROSA e kit.travesseirosazul. Comparação é sempre assim."""
    return (sku or "").strip().lower()


class Produto(Base):
    __tablename__ = "produto"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(120), nullable=False)
    sku_norm: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(300), default="")
    tipo: Mapped[str] = mapped_column(String(10), default=TipoProduto.SIMPLES, index=True)

    codigo_barras: Mapped[str | None] = mapped_column(String(60))
    ml_item_id: Mapped[str | None] = mapped_column(String(30), index=True)
    variacao: Mapped[str | None] = mapped_column(String(200))
    unidade: Mapped[str] = mapped_column(String(10), default="un")

    custo: Mapped[float] = mapped_column(Float, default=0.0)
    imposto: Mapped[float] = mapped_column(Float, default=0.0)
    preco_venda: Mapped[float] = mapped_column(Float, default=0.0)

    estoque_minimo: Mapped[int] = mapped_column(Integer, default=0)
    fornecedor: Mapped[str | None] = mapped_column(String(160))
    localizacao: Mapped[str | None] = mapped_column(String(120))
    foto: Mapped[str | None] = mapped_column(String(400))
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora, onupdate=_agora)

    componentes: Mapped[list[Composicao]] = relationship(
        back_populates="kit",
        foreign_keys="Composicao.kit_id",
        cascade="all, delete-orphan",
    )
    usado_em: Mapped[list[Composicao]] = relationship(
        back_populates="componente", foreign_keys="Composicao.componente_id"
    )
    saldos: Mapped[list[Saldo]] = relationship(
        back_populates="produto", cascade="all, delete-orphan"
    )

    @property
    def eh_kit(self) -> bool:
        return self.tipo == TipoProduto.KIT

    @property
    def rotulo(self) -> str:
        """Nome quando existe; senão o SKU. A carga inicial pode vir sem nome."""
        return (self.nome or "").strip() or self.sku

    def __repr__(self) -> str:
        return f"<Produto {self.sku} ({self.tipo})>"


class Composicao(Base):
    """De que um kit é feito. ESCOPO.md §4.3 — componente é sempre simples."""

    __tablename__ = "composicao"
    __table_args__ = (
        UniqueConstraint("kit_id", "componente_id", name="uq_composicao"),
        CheckConstraint("quantidade >= 1", name="ck_composicao_qtd"),
        CheckConstraint("kit_id != componente_id", name="ck_composicao_nao_recursiva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kit_id: Mapped[int] = mapped_column(ForeignKey("produto.id", ondelete="CASCADE"), index=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("produto.id"), index=True)
    quantidade: Mapped[int] = mapped_column(Integer, default=1)

    kit: Mapped[Produto] = relationship(back_populates="componentes", foreign_keys=[kit_id])
    componente: Mapped[Produto] = relationship(
        back_populates="usado_em", foreign_keys=[componente_id]
    )


class LocalEstoque(Base):
    __tablename__ = "local_estoque"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nome: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(20), default="proprio")
    visivel: Mapped[bool] = mapped_column(Boolean, default=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Saldo(Base):
    """Cache do estoque. Só de produtos SIMPLES — kit não tem saldo."""

    __tablename__ = "saldo"
    __table_args__ = (UniqueConstraint("produto_id", "local_id", name="uq_saldo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(
        ForeignKey("produto.id", ondelete="CASCADE"), index=True
    )
    local_id: Mapped[int] = mapped_column(ForeignKey("local_estoque.id"), index=True)
    quantidade: Mapped[int] = mapped_column(Integer, default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora, onupdate=_agora)

    produto: Mapped[Produto] = relationship(back_populates="saldos")
    local: Mapped[LocalEstoque] = relationship()


class Movimento(Base):
    """Livro-razão imutável. ESCOPO.md §4.1."""

    __tablename__ = "movimento"

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"), index=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("local_estoque.id"))
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    quantidade: Mapped[int] = mapped_column(Integer)          # com sinal: + entra, - sai
    saldo_apos: Mapped[int] = mapped_column(Integer)
    origem: Mapped[str] = mapped_column(String(30), default=OrigemMovimento.MANUAL)
    referencia_externa: Mapped[str | None] = mapped_column(String(80), index=True)

    # Quando a baixa veio de um kit, qual kit foi vendido. É o que torna o histórico
    # legível: "saiu 1 mordedor porque vendeu 1 KIT.MAOPE.ROSA".
    produto_vendido_id: Mapped[int | None] = mapped_column(ForeignKey("produto.id"))

    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lote_importacao.id"), index=True)
    observacao: Mapped[str | None] = mapped_column(Text)
    data_evento: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora, index=True)

    produto: Mapped[Produto] = relationship(foreign_keys=[produto_id])
    produto_vendido: Mapped[Produto | None] = relationship(foreign_keys=[produto_vendido_id])
    local: Mapped[LocalEstoque] = relationship()


# Idempotência garantida pelo BANCO, não pela aplicação (ESCOPO.md §4.3).
#
# O `produto_id` faz parte da chave de propósito: uma venda de kit gera VÁRIOS
# movimentos com a mesma `referencia_externa` (o N.º de venda), um por componente.
# Sem ele, a segunda linha do mesmo kit seria rejeitada como duplicata.
#
# Índice PARCIAL: movimentos manuais têm referencia_externa nula e não competem entre si.
Index(
    "uq_movimento_idempotente",
    Movimento.origem,
    Movimento.referencia_externa,
    Movimento.tipo,
    Movimento.produto_id,
    unique=True,
    sqlite_where=Movimento.referencia_externa.isnot(None),
)


class LoteImportacao(Base):
    __tablename__ = "lote_importacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    arquivo_nome: Mapped[str] = mapped_column(String(300))
    arquivo_hash: Mapped[str | None] = mapped_column(String(64))
    tipo: Mapped[str] = mapped_column(String(40), default="vendas_ml")
    periodo_inicio: Mapped[datetime | None] = mapped_column(DateTime)
    periodo_fim: Mapped[datetime | None] = mapped_column(DateTime)
    linhas_total: Mapped[int] = mapped_column(Integer, default=0)
    linhas_novas: Mapped[int] = mapped_column(Integer, default=0)
    linhas_ignoradas: Mapped[int] = mapped_column(Integer, default=0)
    linhas_pendentes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=StatusLote.RASCUNHO)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime)


class VinculoML(Base):
    """De-para aprendido: uma vez vinculado um SKU órfão, o app nunca mais pergunta."""

    __tablename__ = "vinculo_ml"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id", ondelete="CASCADE"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_agora)

    produto: Mapped[Produto] = relationship()


class Config(Base):
    __tablename__ = "config"

    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(Text, default="")
