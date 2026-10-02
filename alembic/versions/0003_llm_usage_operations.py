"""Rastreia operação, usuário e SIAFI para cada chamada LLM."""

import sqlalchemy as sa

from alembic import op

revision = "0003_llm_usage_operations"
down_revision = "0002_llm_usage_error"


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("llm_usage")}
    if "operation" not in columns:
        op.add_column("llm_usage", sa.Column("operation", sa.String(20), nullable=True))
    if "user_id" not in columns:
        op.add_column("llm_usage", sa.Column("user_id", sa.Integer(), nullable=True))
    if "siafi" not in columns:
        op.add_column("llm_usage", sa.Column("siafi", sa.String(30), nullable=True))


def downgrade():
    for name in ("siafi", "user_id", "operation"):
        if name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("llm_usage")}:
            op.drop_column("llm_usage", name)
