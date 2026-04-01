from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.projection import (
    ComparisonResponse,
    CustomLineCreate,
    CustomLineResponse,
    CustomLineUpdate,
)
from src.services.custom_line_service import CustomLineService
from src.services.projection_service import DEFAULT_LOOKBACK

router = APIRouter(prefix="/custom-lines", tags=["custom lines"])


@router.get("", response_model=list[CustomLineResponse])
async def list_todays_lines(db: AsyncSession = Depends(get_db)):
    """All manually entered lines for today's games."""
    return await CustomLineService(db).get_today()


@router.post("", response_model=CustomLineResponse, status_code=201)
async def add_line(payload: CustomLineCreate, db: AsyncSession = Depends(get_db)):
    """
    Enter a line from your bookmaker.

    market_key options:
      player_points, player_rebounds, player_assists, player_threes,
      player_blocks, player_steals, player_turnovers
    """
    return await CustomLineService(db).create(payload)


@router.get("/compare", response_model=ComparisonResponse)
async def compare_lines(
    lookback: int = Query(
        DEFAULT_LOOKBACK,
        ge=3,
        le=82,
        description="Games to look back for projection",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    The main view: projection vs your entered line for every prop today.
    Shows edge, lean (over/under), hit rate, floor/ceiling.
    Sorted by absolute edge — biggest edges first.
    """
    return await CustomLineService(db).compare_today(lookback)


@router.get("/{line_id}", response_model=CustomLineResponse)
async def get_line(line_id: int, db: AsyncSession = Depends(get_db)):
    return await CustomLineService(db).get_one(line_id)


@router.put("/{line_id}", response_model=CustomLineResponse)
async def update_line(
    line_id: int, payload: CustomLineUpdate, db: AsyncSession = Depends(get_db)
):
    """Adjust any field on an existing line."""
    return await CustomLineService(db).update(line_id, payload)


@router.delete("/{line_id}", status_code=204)
async def delete_line(line_id: int, db: AsyncSession = Depends(get_db)):
    await CustomLineService(db).delete(line_id)
