from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CustomLine(Base):
    __tablename__ = "custom_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id"), nullable=False, index=True
    )
    game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("games.id"), nullable=False, index=True
    )
    # e.g. player_points, player_rebounds, player_assists, player_threes
    market_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # The line (e.g. 27.5)
    over_line: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
