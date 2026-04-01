from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.schemas.props import BestLinesResponse
from src.services.props_service import PropsService

router = APIRouter(prefix="/props", tags=["props"])


@router.get("/best-lines", response_model=BestLinesResponse)
async def get_best_lines(db: AsyncSession = Depends(get_db)):
    """Best available over/under line per player per market across all tracked books."""
    return await PropsService(db).get_best_lines_today()
