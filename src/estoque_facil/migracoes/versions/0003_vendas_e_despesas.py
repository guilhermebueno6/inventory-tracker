"""vendas com valor e despesas

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _tem_tabela(nome: str) -> bool:
    return nome in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # Defensiva pelo mesmo motivo da 0002: bancos das primeiras instalações são
    # "adotados" com um carimbo, então a tabela pode já existir.
    if not _tem_tabela("venda_item"):
        op.create_table(
            "venda_item",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("numero_venda", sa.String(length=80), nullable=False),
            sa.Column("sku_ref", sa.String(length=200), nullable=False),
            sa.Column("produto_id", sa.Integer(), nullable=True),
            sa.Column("titulo", sa.String(length=300), nullable=True),
            sa.Column("quantidade", sa.Integer(), nullable=True),
            sa.Column("devolvidas", sa.Integer(), nullable=True),
            sa.Column("abateu_estoque", sa.Boolean(), nullable=True),
            sa.Column("cancelada", sa.Boolean(), nullable=True),
            sa.Column("local_codigo", sa.String(length=20), nullable=True),
            sa.Column("preco_unitario", sa.Float(), nullable=True),
            sa.Column("receita_produtos", sa.Float(), nullable=True),
            sa.Column("receita_envio", sa.Float(), nullable=True),
            sa.Column("tarifa_venda", sa.Float(), nullable=True),
            sa.Column("tarifa_envio", sa.Float(), nullable=True),
            sa.Column("descontos", sa.Float(), nullable=True),
            sa.Column("cancelamentos", sa.Float(), nullable=True),
            sa.Column("total_liquido", sa.Float(), nullable=True),
            sa.Column("custo_unitario", sa.Float(), nullable=True),
            sa.Column("imposto_unitario", sa.Float(), nullable=True),
            sa.Column("data_venda", sa.DateTime(), nullable=True),
            sa.Column("lote_id", sa.Integer(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.Column("atualizado_em", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["produto_id"], ["produto.id"]),
            sa.ForeignKeyConstraint(["lote_id"], ["lote_importacao.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("numero_venda", "sku_ref", name="uq_venda_item"),
        )
        op.create_index("ix_venda_item_numero_venda", "venda_item", ["numero_venda"])
        op.create_index("ix_venda_item_produto_id", "venda_item", ["produto_id"])
        op.create_index("ix_venda_item_data_venda", "venda_item", ["data_venda"])
        op.create_index("ix_venda_item_lote_id", "venda_item", ["lote_id"])

    if not _tem_tabela("despesa"):
        op.create_table(
            "despesa",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("data", sa.DateTime(), nullable=False),
            sa.Column("descricao", sa.String(length=300), nullable=False),
            sa.Column("categoria", sa.String(length=30), nullable=True),
            sa.Column("valor", sa.Float(), nullable=False),
            sa.Column("observacao", sa.Text(), nullable=True),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.CheckConstraint("valor > 0", name="ck_despesa_valor"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_despesa_data", "despesa", ["data"])
        op.create_index("ix_despesa_categoria", "despesa", ["categoria"])


def downgrade() -> None:
    if _tem_tabela("despesa"):
        op.drop_table("despesa")
    if _tem_tabela("venda_item"):
        op.drop_table("venda_item")
