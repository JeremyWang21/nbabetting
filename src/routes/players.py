from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.player import PlayerSearchResponse
from src.schemas.stats import GameLogResponse, PlayerStatsResponse
from src.services.stats_service import StatsService

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search", response_model=PlayerSearchResponse)
async def search_players(
    q: str = Query(..., min_length=2, description="Player name search query"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return await StatsService(db).search_players(q, limit)


@router.get("/by-team/{team_id}", response_model=PlayerSearchResponse)
async def players_by_team(team_id: int, db: AsyncSession = Depends(get_db)):
    return await StatsService(db).get_players_by_team(team_id)


@router.get("/{player_id}/stats", response_model=PlayerStatsResponse)
async def get_player_stats(player_id: int, db: AsyncSession = Depends(get_db)):
    return await StatsService(db).get_player_stats(player_id)


@router.get("/{player_id}/gamelogs", response_model=list[GameLogResponse])
async def get_player_gamelogs(
    player_id: int,
    limit: int = Query(10, ge=1, le=82),
    db: AsyncSession = Depends(get_db),
):
    return await StatsService(db).get_player_gamelogs(player_id, limit)
