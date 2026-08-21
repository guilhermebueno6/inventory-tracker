"""fornecedor no produto

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _tem_coluna(tabela: str, coluna: str) -> bool:
    inspetor = sa.inspect(op.get_bind())
    return coluna in {c["name"] for c in inspetor.get_columns(tabela)}


def upgrade() -> None:
    # Migração defensiva, por escolha: as primeiras instalações criaram o banco
    # com create_all() e sem controle de versão, então o app "adota" esses bancos
    # carimbando-os como 0001. Se o schema real já estiver adiantado, aplicar a
    # migração cegamente quebraria a atualização — e o conserto óbvio seria
    # apagar o banco. Verificar antes custa três linhas.
    if _tem_coluna("produto", "fornecedor"):
        return
    with op.batch_alter_table("produto", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fornecedor", sa.String(length=160), nullable=True))


def downgrade() -> None:
    if not _tem_coluna("produto", "fornecedor"):
        return
    with op.batch_alter_table("produto", schema=None) as batch_op:
        batch_op.drop_column("fornecedor")
