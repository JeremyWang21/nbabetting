from datetime import date

from pydantic import BaseModel


class TeamSummary(BaseModel):
    id: int
    nba_id: int
    name: str
    abbreviation: str
    city: str

    model_config = {"from_attributes": True}


class GameResponse(BaseModel):
    id: int
    nba_game_id: str
    game_date: date
    home_team_id: int
    away_team_id: int
    status: str
    home_score: int | None
    away_score: int | None
    season: str
    season_type: str

    model_config = {"from_attributes": True}


class TodaysGamesResponse(BaseModel):
    date: date
    games: list[GameResponse]
    count: int
