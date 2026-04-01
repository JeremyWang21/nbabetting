from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.keys import TTL_GAMES_TODAY, games_today
from src.cache.redis_client import cache_get, cache_set
from src.models.game import Game
from src.schemas.game import TodaysGamesResponse


class GameService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_todays_games(self) -> TodaysGamesResponse:
        cache_key = games_today()

        cached = await cache_get(cache_key)
        if cached is not None:
            return TodaysGamesResponse.model_validate(cached)

        today = date.today()
        result = await self.db.execute(
            select(Game).where(Game.game_date == today).order_by(Game.id)
        )
        games = result.scalars().all()
        response = TodaysGamesResponse(date=today, games=list(games), count=len(games))

        await cache_set(cache_key, response.model_dump(), ttl=TTL_GAMES_TODAY)
        return response
