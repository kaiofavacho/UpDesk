"""Aumenta o tamanho da coluna prioridade_Chamado para 20 caracteres

Revision ID: f7aaa4687fc9
Revises: d3b76808690c
Create Date: 2025-10-25 14:08:51.942428
"""

from alembic import op
import sqlalchemy as sa

# Identificadores de revisão
revision = "f7aaa4687fc9"
down_revision = "d3b76808690c"
branch_labels = None
depends_on = None


def upgrade():
    """
    - NÃO mexe mais nas tabelas antigas 'Usuarios' e 'Chamados'
    - Apenas ajusta o tamanho da coluna prioridade_Chamado
    """
    with op.batch_alter_table("Chamado", schema=None) as batch_op:
        batch_op.alter_column(
            "prioridade_Chamado",
            existing_type=sa.VARCHAR(length=15),
            type_=sa.String(length=20),
            existing_nullable=False,
        )


def downgrade():
    """
    Volta o tamanho da coluna prioridade_Chamado para 15 caracteres.
    (Não recria 'Usuarios' nem 'Chamados', pois essas tabelas não existem
    no modelo atual.)
    """
    with op.batch_alter_table("Chamado", schema=None) as batch_op:
        batch_op.alter_column(
            "prioridade_Chamado",
            existing_type=sa.String(length=20),
            type_=sa.VARCHAR(length=15),
            existing_nullable=False,
        )
