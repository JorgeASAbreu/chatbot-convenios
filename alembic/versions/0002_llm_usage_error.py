"""Adiciona erro às métricas persistentes de LLM."""

import sqlalchemy as sa

from alembic import op

revision = "0002_llm_usage_error"
down_revision = "0001_initial"


def upgrade():
    # O 0001 usa metadata atual na homologação inicial; evita duplicar coluna em banco novo.
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("llm_usage")}
    if "error" not in columns:
        op.add_column("llm_usage", sa.Column("error", sa.Text(), nullable=True))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("llm_usage")}
    if "error" in columns:
        op.drop_column("llm_usage", "error")
