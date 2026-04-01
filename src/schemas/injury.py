from datetime import date, datetime

from pydantic import BaseModel


class InjuryReportResponse(BaseModel):
    id: int
    player_id: int
    player_name: str | None = None
    game_id: int | None
    status: str
    injury_description: str | None
    return_date_estimate: date | None
    source: str | None
    reported_at: datetime

    model_config = {"from_attributes": True}


class InjuryListResponse(BaseModel):
    injuries: list[InjuryReportResponse]
    count: int
