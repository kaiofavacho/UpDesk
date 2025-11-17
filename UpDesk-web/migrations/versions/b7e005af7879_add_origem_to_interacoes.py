# Este é um template Mako usado pelo Alembic para gerar scripts de migração de banco de dados.
# Ele define a estrutura para gerenciar a evolução do esquema do banco de dados de forma controlada.

"""add origem to interacoes
# Descrição da migração, fornecida pelo desenvolvedor.

Revision ID: b7e005af7879
# Identificador único para esta migração, crucial para o controle de versão do esquema.
Revises: a608bad9f094
# Identificador da migração anterior, estabelecendo a ordem das migrações.
Create Date: 2025-11-17 15:12:02.475968
# Data e hora da criação desta migração.

"""
from alembic import op
# 'op' fornece operações de banco de dados (DDL) para modificar o esquema.
import sqlalchemy as sa
# 'sa' (SQLAlchemy) é usado para definir tipos de dados e construções de esquema.


# Identificadores de revisão, usados pelo Alembic para rastrear o histórico.
revision = 'b7e005af7879'
# O ID da revisão atual.
down_revision = 'a608bad9f094'
# O ID da revisão para a qual esta migração reverte.
branch_labels = None
# Rótulos de ramificação, úteis para migrações em ambientes de desenvolvimento paralelos.
depends_on = None
# Dependências de outras migrações, garantindo a ordem de execução.


def upgrade():
    with op.batch_alter_table('Interacoes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origem', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('Interacoes', schema=None) as batch_op:
        batch_op.drop_column('origem')
