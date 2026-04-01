from datetime import datetime

from pydantic import BaseModel


class BookmakerLine(BaseModel):
    bookmaker: str
    over_line: float | None
    over_price: int | None
    under_price: int | None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class PlayerPropLines(BaseModel):
    player_id: int
    player_name: str
    game_id: int
    market_key: str
    lines: list[BookmakerLine]


class BestLine(BaseModel):
    """Best available over and under across all tracked bookmakers."""
    player_id: int
    player_name: str
    game_id: int
    market_key: str
    best_over_line: float | None
    best_over_book: str | None
    best_over_price: int | None
    best_under_price: int | None
    best_under_book: str | None
    fetched_at: datetime | None


class BestLinesResponse(BaseModel):
    props: list[BestLine]
    count: int
