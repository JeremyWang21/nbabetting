from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class PlayerSeasonAverages(Base):
    __tablename__ = "player_season_averages"
    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "season",
            name="uq_player_season_averages_player_id_season",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False, index=True
    )
    season: Mapped[str] = mapped_column(String(10), nullable=False)
    games_played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mpg: Mapped[float | None] = mapped_column(Float, nullable=True)
    ppg: Mapped[float | None] = mapped_column(Float, nullable=True)
    rpg: Mapped[float | None] = mapped_column(Float, nullable=True)
    apg: Mapped[float | None] = mapped_column(Float, nullable=True)
    spg: Mapped[float | None] = mapped_column(Float, nullable=True)
    bpg: Mapped[float | None] = mapped_column(Float, nullable=True)
    fg_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fg3_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ft_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
