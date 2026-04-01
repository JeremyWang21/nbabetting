from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class InjuryReport(Base):
    __tablename__ = "injury_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False, index=True
    )
    # nullable — a player can have an injury status without a specific game attached
    game_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("games.id"), nullable=True, index=True
    )
    # OUT, GTD (game-time decision), QUESTIONABLE, PROBABLE, AVAILABLE
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    injury_description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    return_date_estimate: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
