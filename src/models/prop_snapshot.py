from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class PropSnapshot(Base):
    __tablename__ = "prop_snapshots"
    __table_args__ = (
        # Composite index for the most common query: "give me all lines for
        # this player in this game for this market, ordered by time"
        Index(
            "ix_prop_snapshots_lookup",
            "player_id",
            "game_id",
            "market_key",
            "fetched_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False
    )
    game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("games.id"), nullable=False
    )
    # e.g. player_points, player_rebounds, player_assists, player_threes
    market_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. draftkings, fanduel, betmgm, caesars, pinnacle
    bookmaker: Mapped[str] = mapped_column(String(50), nullable=False)
    over_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    over_price: Mapped[int | None] = mapped_column(Integer, nullable=True)   # American odds
    under_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # American odds
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
