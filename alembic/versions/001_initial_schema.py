"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── teams ──────────────────────────────────────────────────────────────────
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nba_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("abbreviation", sa.String(5), nullable=False),
        sa.Column("city", sa.String(50), nullable=False),
        sa.Column("conference", sa.String(10), nullable=True),
        sa.Column("division", sa.String(20), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        sa.UniqueConstraint("nba_id", name="uq_teams_nba_id"),
    )
    op.create_index("ix_teams_nba_id", "teams", ["nba_id"])

    # ── players ────────────────────────────────────────────────────────────────
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nba_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("first_name", sa.String(50), nullable=False),
        sa.Column("last_name", sa.String(50), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.String(10), nullable=True),
        sa.Column("jersey_number", sa.String(5), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("id", name="pk_players"),
        sa.UniqueConstraint("nba_id", name="uq_players_nba_id"),
    )
    op.create_index("ix_players_nba_id", "players", ["nba_id"])
    op.create_index("ix_players_team_id", "players", ["team_id"])

    # ── games ──────────────────────────────────────────────────────────────────
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nba_game_id", sa.String(20), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("season", sa.String(10), nullable=False),
        sa.Column(
            "season_type",
            sa.String(20),
            nullable=False,
            server_default="Regular Season",
        ),
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
            ["home_team_id"], ["teams.id"], name="fk_games_home_team_id_teams"
        ),
        sa.ForeignKeyConstraint(
            ["away_team_id"], ["teams.id"], name="fk_games_away_team_id_teams"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_games"),
        sa.UniqueConstraint("nba_game_id", name="uq_games_nba_game_id"),
    )
    op.create_index("ix_games_nba_game_id", "games", ["nba_game_id"])
    op.create_index("ix_games_game_date", "games", ["game_date"])

    # ── player_game_logs ───────────────────────────────────────────────────────
    op.create_table(
        "player_game_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.String(10), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("rebounds", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("steals", sa.Integer(), nullable=True),
        sa.Column("blocks", sa.Integer(), nullable=True),
        sa.Column("turnovers", sa.Integer(), nullable=True),
        sa.Column("fg_made", sa.Integer(), nullable=True),
        sa.Column("fg_attempted", sa.Integer(), nullable=True),
        sa.Column("fg3_made", sa.Integer(), nullable=True),
        sa.Column("fg3_attempted", sa.Integer(), nullable=True),
        sa.Column("ft_made", sa.Integer(), nullable=True),
        sa.Column("ft_attempted", sa.Integer(), nullable=True),
        sa.Column("plus_minus", sa.Integer(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="fk_player_game_logs_player_id_players"
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name="fk_player_game_logs_game_id_games"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_player_game_logs"),
        sa.UniqueConstraint(
            "player_id", "game_id", name="uq_player_game_logs_player_id_game_id"
        ),
    )
    op.create_index("ix_player_game_logs_player_id", "player_game_logs", ["player_id"])
    op.create_index("ix_player_game_logs_game_id", "player_game_logs", ["game_id"])

    # ── player_season_averages ─────────────────────────────────────────────────
    op.create_table(
        "player_season_averages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.String(10), nullable=False),
        sa.Column("games_played", sa.Integer(), nullable=True),
        sa.Column("mpg", sa.Float(), nullable=True),
        sa.Column("ppg", sa.Float(), nullable=True),
        sa.Column("rpg", sa.Float(), nullable=True),
        sa.Column("apg", sa.Float(), nullable=True),
        sa.Column("spg", sa.Float(), nullable=True),
        sa.Column("bpg", sa.Float(), nullable=True),
        sa.Column("fg_pct", sa.Float(), nullable=True),
        sa.Column("fg3_pct", sa.Float(), nullable=True),
        sa.Column("ft_pct", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name="fk_player_season_averages_player_id_players",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_player_season_averages"),
        sa.UniqueConstraint(
            "player_id",
            "season",
            name="uq_player_season_averages_player_id_season",
        ),
    )
    op.create_index(
        "ix_player_season_averages_player_id", "player_season_averages", ["player_id"]
    )

    # ── injury_reports ─────────────────────────────────────────────────────────
    op.create_table(
        "injury_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("injury_description", sa.String(200), nullable=True),
        sa.Column("return_date_estimate", sa.Date(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="fk_injury_reports_player_id_players"
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name="fk_injury_reports_game_id_games"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_injury_reports"),
    )
    op.create_index("ix_injury_reports_player_id", "injury_reports", ["player_id"])
    op.create_index("ix_injury_reports_game_id", "injury_reports", ["game_id"])
    op.create_index("ix_injury_reports_reported_at", "injury_reports", ["reported_at"])

    # ── prop_snapshots ─────────────────────────────────────────────────────────
    op.create_table(
        "prop_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("market_key", sa.String(50), nullable=False),
        sa.Column("bookmaker", sa.String(50), nullable=False),
        sa.Column("over_line", sa.Float(), nullable=True),
        sa.Column("over_price", sa.Integer(), nullable=True),
        sa.Column("under_price", sa.Integer(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name="fk_prop_snapshots_player_id_players"
        ),
        sa.ForeignKeyConstraint(
            ["game_id"], ["games.id"], name="fk_prop_snapshots_game_id_games"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prop_snapshots"),
    )
    op.create_index(
        "ix_prop_snapshots_lookup",
        "prop_snapshots",
        ["player_id", "game_id", "market_key", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_table("prop_snapshots")
    op.drop_table("injury_reports")
    op.drop_table("player_season_averages")
    op.drop_table("player_game_logs")
    op.drop_table("games")
    op.drop_table("players")
    op.drop_table("teams")
