from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.keys import (
    TTL_PLAYER_GAMELOGS,
    TTL_PLAYER_STATS,
    player_gamelogs,
    player_stats,
)
from src.cache.redis_client import cache_get, cache_set
from src.models.game import Game
from src.models.game_log import PlayerGameLog
from src.models.player import Player
from src.models.season_averages import PlayerSeasonAverages
from src.models.team import Team
from src.schemas.player import PlayerResponse, PlayerSearchResponse
from src.schemas.stats import GameLogResponse, PlayerStatsResponse, SeasonAveragesResponse


class StatsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search_players(self, query: str, limit: int = 20) -> PlayerSearchResponse:
        result = await self.db.execute(
            select(Player)
            .where(Player.full_name.ilike(f"%{query}%"), Player.is_active.is_(True))
            .limit(limit)
        )
        players = result.scalars().all()

        team_ids = {p.team_id for p in players if p.team_id}
        team_abbrs: dict[int, str] = {}
        if team_ids:
            team_result = await self.db.execute(
                select(Team.id, Team.abbreviation).where(Team.id.in_(team_ids))
            )
            team_abbrs = {row.id: row.abbreviation for row in team_result}

        enriched = [
            PlayerResponse(
                **{c: getattr(p, c) for c in Player.__table__.columns.keys()},
                team_abbreviation=team_abbrs.get(p.team_id) if p.team_id else None,
            )
            for p in players
        ]
        return PlayerSearchResponse(players=enriched, total=len(enriched))

    async def get_players_by_team(self, team_id: int) -> PlayerSearchResponse:
        result = await self.db.execute(
            select(Player)
            .where(Player.team_id == team_id, Player.is_active.is_(True))
            .order_by(Player.full_name)
        )
        players = result.scalars().all()

        team_result = await self.db.execute(
            select(Team.id, Team.abbreviation).where(Team.id == team_id)
        )
        row = team_result.first()
        abbr = row.abbreviation if row else None

        enriched = [
            PlayerResponse(
                **{c: getattr(p, c) for c in Player.__table__.columns.keys()},
                team_abbreviation=abbr,
            )
            for p in players
        ]
        return PlayerSearchResponse(players=enriched, total=len(enriched))

    async def get_player_stats(self, player_id: int) -> PlayerStatsResponse:
        cache_key = player_stats(player_id)

        cached = await cache_get(cache_key)
        if cached is not None:
            return PlayerStatsResponse.model_validate(cached)

        player = await self.db.get(Player, player_id)
        if player is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Player not found")

        avg_result = await self.db.execute(
            select(PlayerSeasonAverages)
            .where(PlayerSeasonAverages.player_id == player_id)
            .order_by(PlayerSeasonAverages.season.desc())
            .limit(1)
        )
        season_avg = avg_result.scalar_one_or_none()
        recent = await self._get_gamelogs_with_dates(player_id, limit=5)

        response = PlayerStatsResponse(
            player_id=player_id,
            player_name=player.full_name,
            season_averages=SeasonAveragesResponse.model_validate(season_avg) if season_avg else None,
            recent_games=recent,
        )

        await cache_set(cache_key, response.model_dump(), ttl=TTL_PLAYER_STATS)
        return response

    async def get_player_gamelogs(self, player_id: int, limit: int = 10) -> list[GameLogResponse]:
        cache_key = player_gamelogs(player_id, limit)

        cached = await cache_get(cache_key)
        if cached is not None:
            return [GameLogResponse.model_validate(row) for row in cached]

        rows = await self._get_gamelogs_with_dates(player_id, limit)

        await cache_set(
            cache_key,
            [r.model_dump() for r in rows],
            ttl=TTL_PLAYER_GAMELOGS,
        )
        return rows

    async def _get_gamelogs_with_dates(
        self, player_id: int, limit: int
    ) -> list[GameLogResponse]:
        result = await self.db.execute(
            select(
                PlayerGameLog,
                Game.game_date,
                Game.home_team_id,
                Game.away_team_id,
            )
            .join(Game, PlayerGameLog.game_id == Game.id)
            .where(PlayerGameLog.player_id == player_id)
            .order_by(Game.game_date.desc())
            .limit(limit)
        )
        rows = result.all()
        if not rows:
            return []

        player = await self.db.get(Player, player_id)
        player_team_id = player.team_id if player else None

        team_ids = {r.home_team_id for r in rows} | {r.away_team_id for r in rows}
        team_result = await self.db.execute(
            select(Team.id, Team.abbreviation).where(Team.id.in_(team_ids))
        )
        team_abbr: dict[int, str] = {row.id: row.abbreviation for row in team_result}

        logs = []
        for row in rows:
            log: PlayerGameLog = row[0]
            opp_id = (
                row.away_team_id
                if player_team_id and row.home_team_id == player_team_id
                else row.home_team_id
            )
            logs.append(
                GameLogResponse(
                    id=log.id,
                    player_id=log.player_id,
                    game_id=log.game_id,
                    game_date=row.game_date,
                    opponent_abbreviation=team_abbr.get(opp_id),
                    minutes=log.minutes,
                    points=log.points,
                    rebounds=log.rebounds,
                    assists=log.assists,
                    steals=log.steals,
                    blocks=log.blocks,
                    turnovers=log.turnovers,
                    fg_made=log.fg_made,
                    fg_attempted=log.fg_attempted,
                    fg3_made=log.fg3_made,
                    fg3_attempted=log.fg3_attempted,
                    ft_made=log.ft_made,
                    ft_attempted=log.ft_attempted,
                    plus_minus=log.plus_minus,
                    fetched_at=log.fetched_at,
                )
            )
        return logs
