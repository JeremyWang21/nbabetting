from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.projection import ProjectionResult
from src.services.projection_service import DEFAULT_LOOKBACK, ProjectionService

router = APIRouter(prefix="/projections", tags=["projections"])

MARKETS = list(__import__("src.services.projection_service", fromlist=["MARKET_TO_FIELD"]).MARKET_TO_FIELD.keys())


@router.get("/today", response_model=list[ProjectionResult])
async def get_todays_projections(
    lookback: int = Query(DEFAULT_LOOKBACK, ge=3, le=82, description="Games to look back"),
    db: AsyncSession = Depends(get_db),
):
    """
    Projections for all players in today's games across all markets.
    Sorted by player_id then market.
    """
    return await ProjectionService(db).project_all_today(lookback)


@router.get("/{player_id}", response_model=list[ProjectionResult])
async def get_player_projections(
    player_id: int,
    game_id: int = Query(..., description="Game ID to project for"),
    lookback: int = Query(DEFAULT_LOOKBACK, ge=3, le=82),
    db: AsyncSession = Depends(get_db),
):
    """All market projections for a specific player in a specific game."""
    return await ProjectionService(db).project_player_all_markets(
        player_id, game_id, lookback
    )


@router.get("/{player_id}/{market_key}", response_model=ProjectionResult | None)
async def get_player_market_projection(
    player_id: int,
    market_key: str,
    game_id: int = Query(..., description="Game ID to project for"),
    lookback: int = Query(DEFAULT_LOOKBACK, ge=3, le=82),
    db: AsyncSession = Depends(get_db),
):
    """Single market projection for a player (e.g. player_points)."""
    return await ProjectionService(db).project_player(
        player_id, game_id, market_key, lookback
    )
