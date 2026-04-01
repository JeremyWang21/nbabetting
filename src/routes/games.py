from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.game import TodaysGamesResponse
from src.schemas.props import BestLinesResponse
from src.services.game_service import GameService
from src.services.props_service import PropsService

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/today", response_model=TodaysGamesResponse)
async def get_todays_games(db: AsyncSession = Depends(get_db)):
    return await GameService(db).get_todays_games()


@router.get("/{game_id}/props", response_model=BestLinesResponse)
async def get_game_props(game_id: int, db: AsyncSession = Depends(get_db)):
    return await PropsService(db).get_game_props(game_id)
