"""Completa a chave estrangeira de llm_usage.user_id em bancos existentes."""

import sqlalchemy as sa

from alembic import op

revision = "0004_llm_usage_user_fk"
down_revision = "0003_llm_usage_operations"


def upgrade():
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("llm_usage")
    if not any("user_id" in fk["constrained_columns"] for fk in foreign_keys):
        op.create_foreign_key(
            "fk_llm_usage_user_id_usuarios", "llm_usage", "usuarios", ["user_id"], ["id"]
        )


def downgrade():
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("llm_usage")
    if any(fk["name"] == "fk_llm_usage_user_id_usuarios" for fk in foreign_keys):
        op.drop_constraint("fk_llm_usage_user_id_usuarios", "llm_usage", type_="foreignkey")
