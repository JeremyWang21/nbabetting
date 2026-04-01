from datetime import date, datetime

from pydantic import BaseModel


class GameLogResponse(BaseModel):
    id: int
    player_id: int
    game_id: int
    game_date: date | None = None
    opponent_abbreviation: str | None = None
    minutes: str | None
    points: int | None
    rebounds: int | None
    assists: int | None
    steals: int | None
    blocks: int | None
    turnovers: int | None
    fg_made: int | None
    fg_attempted: int | None
    fg3_made: int | None
    fg3_attempted: int | None
    ft_made: int | None
    ft_attempted: int | None
    plus_minus: int | None
    fetched_at: datetime

    model_config = {"from_attributes": True}


class SeasonAveragesResponse(BaseModel):
    player_id: int
    season: str
    games_played: int | None
    mpg: float | None
    ppg: float | None
    rpg: float | None
    apg: float | None
    spg: float | None
    bpg: float | None
    fg_pct: float | None
    fg3_pct: float | None
    ft_pct: float | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlayerStatsResponse(BaseModel):
    player_id: int
    player_name: str
    season_averages: SeasonAveragesResponse | None
    recent_games: list[GameLogResponse]
