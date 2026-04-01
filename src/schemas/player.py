from pydantic import BaseModel


class PlayerBase(BaseModel):
    nba_id: int
    full_name: str
    first_name: str
    last_name: str
    team_id: int | None
    position: str | None
    jersey_number: str | None
    is_active: bool


class PlayerResponse(PlayerBase):
    id: int

    model_config = {"from_attributes": True}


class PlayerSearchResponse(BaseModel):
    players: list[PlayerResponse]
    total: int
