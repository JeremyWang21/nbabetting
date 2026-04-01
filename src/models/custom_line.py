from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class CustomLine(Base):
    """
    A prop line entered manually by the user from their bookmaker.
    Compared against the statistical projection to find edges.
    """

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
    # Your bookmaker's name (free text — e.g. "DraftKings", "FanDuel", "my bookie")
    bookmaker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # The line your book is offering (e.g. 27.5)
    over_line: Mapped[float] = mapped_column(Float, nullable=False)
    # American odds — optional, enter if you have them
    over_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    under_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Free-text note (e.g. "back-to-back", "questionable starter")
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
