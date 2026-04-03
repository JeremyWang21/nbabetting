from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.keys import TTL_GAMES_TODAY, games_today
from src.cache.redis_client import cache_get, cache_set
from src.models.game import Game
from src.models.team import Team
from src.schemas.game import GameResponse, TodaysGamesResponse
from src.utils.date_utils import today_et


class GameService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_todays_games(self) -> TodaysGamesResponse:
        cache_key = games_today()

        cached = await cache_get(cache_key)
        if cached is not None:
            return TodaysGamesResponse.model_validate(cached)

        finished = {"final", "final/ot", "final/2ot", "final/3ot"}
        today = today_et()
        all_today, _ = await self._fetch_games_for_date(today)
        upcoming_today = [g for g in all_today if g.status.lower() not in finished]
        display_date = today

        if upcoming_today:
            # Games still in progress or not yet started today
            games = upcoming_today
        elif all_today:
            # All of today's games are done — show full tomorrow slate
            tomorrow = today + timedelta(days=1)
            all_tomorrow, _ = await self._fetch_games_for_date(tomorrow)
            games, display_date = (all_tomorrow, tomorrow) if all_tomorrow else ([], today)
        else:
            # No games today at all — show tomorrow
            tomorrow = today + timedelta(days=1)
            all_tomorrow, _ = await self._fetch_games_for_date(tomorrow)
            games, display_date = (all_tomorrow, tomorrow) if all_tomorrow else ([], today)

        enriched = await self._enrich(games)
        response = TodaysGamesResponse(date=display_date, games=enriched, count=len(enriched))
        # Short TTL so refresh picks up tomorrow's slate quickly once today finishes
        await cache_set(cache_key, response.model_dump(), ttl=TTL_GAMES_TODAY)
        return response

    async def _fetch_games_for_date(self, d: date):
        result = await self.db.execute(
            select(Game).where(Game.game_date == d).order_by(Game.id)
        )
        return result.scalars().all(), d

    async def _enrich(self, games) -> list[GameResponse]:
        if not games:
            return []
        team_ids = {g.home_team_id for g in games} | {g.away_team_id for g in games}
        team_result = await self.db.execute(
            select(Team.id, Team.abbreviation, Team.name).where(Team.id.in_(team_ids))
        )
        teams = {row.id: row for row in team_result}
        return [
            GameResponse(
                id=g.id,
                nba_game_id=g.nba_game_id,
                game_date=g.game_date,
                home_team_id=g.home_team_id,
                away_team_id=g.away_team_id,
                home_team_abbr=teams[g.home_team_id].abbreviation if g.home_team_id in teams else None,
                away_team_abbr=teams[g.away_team_id].abbreviation if g.away_team_id in teams else None,
                home_team_name=teams[g.home_team_id].name if g.home_team_id in teams else None,
                away_team_name=teams[g.away_team_id].name if g.away_team_id in teams else None,
                status=g.status,
                home_score=g.home_score,
                away_score=g.away_score,
                season=g.season,
                season_type=g.season_type,
            )
            for g in games
        ]
