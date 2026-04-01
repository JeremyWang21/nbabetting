"""add team_defensive_stats table

Revision ID: 003
Revises: 002
Create Date: 2026-04-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_defensive_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.String(10), nullable=False),
        sa.Column("games_played", sa.Integer(), nullable=True),
        sa.Column("opp_pts_pg", sa.Float(), nullable=True),
        sa.Column("opp_reb_pg", sa.Float(), nullable=True),
        sa.Column("opp_ast_pg", sa.Float(), nullable=True),
        sa.Column("opp_fg3m_pg", sa.Float(), nullable=True),
        sa.Column("opp_stl_pg", sa.Float(), nullable=True),
        sa.Column("opp_blk_pg", sa.Float(), nullable=True),
        sa.Column("opp_tov_pg", sa.Float(), nullable=True),
        sa.Column("def_rating", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name="fk_team_defensive_stats_team_id_teams",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_team_defensive_stats"),
        sa.UniqueConstraint(
            "team_id", "season", name="uq_team_defensive_stats_team_id_season"
        ),
    )
    op.create_index("ix_team_defensive_stats_team_id", "team_defensive_stats", ["team_id"])


def downgrade() -> None:
    op.drop_table("team_defensive_stats")
