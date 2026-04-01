"""add custom_lines table

Revision ID: 002
Revises: 001
Create Date: 2026-04-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "custom_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("market_key", sa.String(50), nullable=False),
        sa.Column("bookmaker", sa.String(50), nullable=True),
        sa.Column("over_line", sa.Float(), nullable=False),
        sa.Column("over_price", sa.Integer(), nullable=True),
        sa.Column("under_price", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="fk_custom_lines_player_id_players"
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name="fk_custom_lines_game_id_games"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_custom_lines"),
    )
    op.create_index("ix_custom_lines_player_id", "custom_lines", ["player_id"])
    op.create_index("ix_custom_lines_game_id", "custom_lines", ["game_id"])


def downgrade() -> None:
    op.drop_table("custom_lines")
