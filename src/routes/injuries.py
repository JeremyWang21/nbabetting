from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.injury import InjuryListResponse, InjuryReportResponse
from src.services.injury_service import InjuryService

router = APIRouter(prefix="/injuries", tags=["injuries"])


@router.get("", response_model=InjuryListResponse)
async def get_injuries(db: AsyncSession = Depends(get_db)):
    """Today's full injury report."""
    return await InjuryService(db).get_todays_injuries()


@router.get("/{player_id}", response_model=InjuryReportResponse | None)
async def get_player_injury(player_id: int, db: AsyncSession = Depends(get_db)):
    return await InjuryService(db).get_player_injury_status(player_id)
