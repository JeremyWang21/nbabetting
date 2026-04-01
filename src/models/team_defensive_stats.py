from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class TeamDefensiveStats(Base):
    """
    Season-to-date opponent stats allowed per game, per team.
    Used to compute matchup adjustment factors for projections.

    Source: nba_api LeagueDashTeamStats with measure_type="Opponent", per_mode="PerGame"

    Adjustment logic:
      factor = team_allowed_stat / league_avg_allowed_stat
      adjusted_projection = base_projection * factor

    factor > 1.0  → opponent is worse than average at defending this stat → project higher
    factor < 1.0  → opponent is better than average → project lower
    """

    __tablename__ = "team_defensive_stats"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "season", name="uq_team_defensive_stats_team_id_season"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id"), nullable=False, index=True
    )
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    games_played: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Opponent per-game stats allowed (what the team gives up)
    opp_pts_pg: Mapped[float | None] = mapped_column(Float, nullable=True)   # points
    opp_reb_pg: Mapped[float | None] = mapped_column(Float, nullable=True)   # rebounds
    opp_ast_pg: Mapped[float | None] = mapped_column(Float, nullable=True)   # assists
    opp_fg3m_pg: Mapped[float | None] = mapped_column(Float, nullable=True)  # 3-pointers made
    opp_stl_pg: Mapped[float | None] = mapped_column(Float, nullable=True)   # steals allowed (opp steals)
    opp_blk_pg: Mapped[float | None] = mapped_column(Float, nullable=True)   # blocks allowed
    opp_tov_pg: Mapped[float | None] = mapped_column(Float, nullable=True)   # turnovers forced

    # Defensive rating: points allowed per 100 possessions
    def_rating: Mapped[float | None] = mapped_column(Float, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
