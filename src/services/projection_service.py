"""
Projection engine — EWMA base projection + matchup adjustment.

Two-step:
  1. EWMA of last N games (decay=0.85, most recent = highest weight)
  2. Multiply by opponent_allowed / league_avg_allowed for the market's def stat

Results are cached in Redis (TTL_PROJECTIONS) and busted after
ingest_game_logs or ingest_defensive_stats writes.
"""

import statistics
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.keys import (
    TTL_PROJECTIONS,
    projections_player,
    projections_today,
)
from src.cache.redis_client import cache_get, cache_set
from src.ingestion.nba_stats_ingester import CURRENT_SEASON
from src.models.game import Game
from src.models.game_log import PlayerGameLog
from src.models.player import Player
from src.models.team import Team
from src.models.team_defensive_stats import TeamDefensiveStats
from src.schemas.projection import ProjectionResult

DEFAULT_LOOKBACK = 15
EWMA_DECAY = 0.85

MARKET_TO_FIELD: dict[str, str] = {
    "player_points": "points",
    "player_rebounds": "rebounds",
    "player_assists": "assists",
    "player_threes": "fg3_made",
    "player_blocks": "blocks",
    "player_steals": "steals",
    "player_turnovers": "turnovers",
}

MARKET_TO_DEF_FIELD: dict[str, str | None] = {
    "player_points": "opp_pts_pg",
    "player_rebounds": "opp_reb_pg",
    "player_assists": "opp_ast_pg",
    "player_threes": "opp_fg3m_pg",
    "player_blocks": None,
    "player_steals": None,
    "player_turnovers": None,
}


class ProjectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._league_avgs: dict[str, float] | None = None

    async def project_player(
        self,
        player_id: int,
        game_id: int,
        market_key: str,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> ProjectionResult | None:
        if market_key not in MARKET_TO_FIELD:
            return None

        player = await self.db.get(Player, player_id)
        if player is None:
            return None
        game = await self.db.get(Game, game_id)
        if game is None:
            return None

        opponent_abbr, opponent_team_id = await self._get_opponent_info(game, player)
        values = await self._get_recent_values(
            player_id, MARKET_TO_FIELD[market_key], lookback
        )
        if not values:
            return None

        proj = _compute_projection(values)

        matchup_factor = 1.0
        matchup_label: str | None = None
        def_field = MARKET_TO_DEF_FIELD.get(market_key)
        if def_field and opponent_team_id:
            def_stats = await self._get_team_def_stats(opponent_team_id)
            league_avg = await self._get_league_avg(def_field)
            if def_stats and league_avg and league_avg > 0:
                opp_val = getattr(def_stats, def_field)
                if opp_val is not None and opp_val > 0:
                    matchup_factor = opp_val / league_avg
                    matchup_label = _matchup_label(matchup_factor)

        return ProjectionResult(
            player_id=player_id,
            player_name=player.full_name,
            game_id=game_id,
            game_date=game.game_date,
            opponent=opponent_abbr,
            market_key=market_key,
            projected_value=proj["projected_value"],
            adjusted_projection=round(proj["projected_value"] * matchup_factor, 2),
            matchup_factor=round(matchup_factor, 3),
            matchup_label=matchup_label,
            avg_last_n=proj["avg"],
            sample_size=proj["n"],
            floor=proj["floor"],
            ceiling=proj["ceiling"],
            std_dev=proj["std_dev"],
            variance=proj["variance"],
        )

    async def project_player_all_markets(
        self,
        player_id: int,
        game_id: int,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> list[ProjectionResult]:
        cache_key = projections_player(player_id, game_id, lookback)

        cached = await cache_get(cache_key)
        if cached is not None:
            return [ProjectionResult.model_validate(r) for r in cached]

        results = []
        for market_key in MARKET_TO_FIELD:
            result = await self.project_player(player_id, game_id, market_key, lookback)
            if result is not None:
                results.append(result)

        if results:
            await cache_set(
                cache_key,
                [r.model_dump() for r in results],
                ttl=TTL_PROJECTIONS,
            )
        return results

    async def project_all_today(
        self, lookback: int = DEFAULT_LOOKBACK
    ) -> list[ProjectionResult]:
        cache_key = projections_today(lookback)

        cached = await cache_get(cache_key)
        if cached is not None:
            return [ProjectionResult.model_validate(r) for r in cached]

        today = date.today()
        game_result = await self.db.execute(
            select(Game).where(Game.game_date == today)
        )
        games = game_result.scalars().all()
        if not games:
            return []

        from sqlalchemy import distinct
        player_result = await self.db.execute(
            select(distinct(PlayerGameLog.player_id))
        )
        player_ids = [row[0] for row in player_result]

        player_team_result = await self.db.execute(
            select(Player.id, Player.team_id).where(Player.id.in_(player_ids))
        )
        player_team: dict[int, int | None] = {
            row.id: row.team_id for row in player_team_result
        }

        game_team_ids: dict[int, set[int]] = {
            g.id: {g.home_team_id, g.away_team_id} for g in games
        }

        projections: list[ProjectionResult] = []
        for pid in player_ids:
            team_id = player_team.get(pid)
            if team_id is None:
                continue
            game_id = next(
                (gid for gid, tids in game_team_ids.items() if team_id in tids), None
            )
            if game_id is None:
                continue
            for market_key in MARKET_TO_FIELD:
                proj = await self.project_player(pid, game_id, market_key, lookback)
                if proj is not None:
                    projections.append(proj)

        if projections:
            await cache_set(
                cache_key,
                [p.model_dump() for p in projections],
                ttl=TTL_PROJECTIONS,
            )
        return projections

    def hit_rate(self, values: list[float], line: float) -> tuple[float, float]:
        if not values:
            return 0.0, 0.0
        over = sum(1 for v in values if v > line) / len(values)
        under = sum(1 for v in values if v < line) / len(values)
        return round(over, 3), round(under, 3)

    async def get_recent_values_for_market(
        self,
        player_id: int,
        market_key: str,
        lookback: int = DEFAULT_LOOKBACK,
    ) -> list[float]:
        field = MARKET_TO_FIELD.get(market_key)
        if field is None:
            return []
        return await self._get_recent_values(player_id, field, lookback)

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _get_recent_values(
        self, player_id: int, field: str, lookback: int
    ) -> list[float]:
        result = await self.db.execute(
            select(PlayerGameLog)
            .join(Game, PlayerGameLog.game_id == Game.id)
            .where(
                PlayerGameLog.player_id == player_id,
                getattr(PlayerGameLog, field).is_not(None),
            )
            .order_by(Game.game_date.desc())
            .limit(lookback)
        )
        return [float(getattr(log, field)) for log in result.scalars().all()]

    async def _get_opponent_info(
        self, game: Game, player: Player
    ) -> tuple[str | None, int | None]:
        if player.team_id is None:
            return None, None
        opp_id = (
            game.away_team_id
            if game.home_team_id == player.team_id
            else game.home_team_id
        )
        team = await self.db.get(Team, opp_id)
        return (team.abbreviation, opp_id) if team else (None, None)

    async def _get_team_def_stats(self, team_id: int) -> TeamDefensiveStats | None:
        result = await self.db.execute(
            select(TeamDefensiveStats).where(
                TeamDefensiveStats.team_id == team_id,
                TeamDefensiveStats.season == CURRENT_SEASON,
            )
        )
        return result.scalar_one_or_none()

    async def _get_league_avg(self, def_field: str) -> float | None:
        if self._league_avgs is None:
            self._league_avgs = await self._compute_league_avgs()
        return self._league_avgs.get(def_field)

    async def _compute_league_avgs(self) -> dict[str, float]:
        result = await self.db.execute(
            select(TeamDefensiveStats).where(
                TeamDefensiveStats.season == CURRENT_SEASON
            )
        )
        all_stats = result.scalars().all()
        if not all_stats:
            return {}
        avgs: dict[str, float] = {}
        for field in {f for f in MARKET_TO_DEF_FIELD.values() if f}:
            vals = [getattr(s, field) for s in all_stats if getattr(s, field) is not None]
            if vals:
                avgs[field] = statistics.mean(vals)
        return avgs


# ── Pure math ─────────────────────────────────────────────────────────────────

def _compute_projection(values: list[float]) -> dict:
    n = len(values)
    weights = [EWMA_DECAY**i for i in range(n)]
    total = sum(weights)
    ewma = sum(v * w for v, w in zip(values, weights)) / total
    avg = statistics.mean(values)
    std_dev = statistics.pstdev(values) if n > 1 else 0.0
    sorted_vals = sorted(values)
    return {
        "projected_value": round(ewma, 2),
        "avg": round(avg, 2),
        "n": n,
        "floor": round(_percentile(sorted_vals, 25), 2),
        "ceiling": round(_percentile(sorted_vals, 75), 2),
        "std_dev": round(std_dev, 2),
        "variance": round(std_dev ** 2, 2),
    }


def _percentile(sorted_vals: list[float], pct: int) -> float:
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    idx = (pct / 100) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] * (1 - (idx - lo)) + sorted_vals[hi] * (idx - lo)


def _matchup_label(factor: float) -> str:
    if factor >= 1.10:
        return "very favorable"
    if factor >= 1.04:
        return "favorable"
    if factor >= 0.97:
        return "neutral"
    if factor >= 0.91:
        return "tough"
    return "very tough"
