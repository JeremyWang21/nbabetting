"""
Team defensive stats ingestion via nba_api.

Uses two endpoints in one pass:
  1. LeagueDashTeamStats (measure_type="Opponent", per_mode="PerGame")
     → opp_pts_pg, opp_reb_pg, opp_ast_pg, opp_fg3m_pg, opp_tov_pg, opp_stl_pg, opp_blk_pg

  2. LeagueDashTeamStats (measure_type="Advanced", per_mode="PerGame")
     → def_rating (DEF_RATING column)

Runs daily at 5am (after game logs at 4am) so the defensive numbers
reflect last night's games.
"""

import asyncio
import logging
from functools import partial

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.cache.keys import PATTERN_PROJECTIONS_ALL
from src.cache.redis_client import cache_delete_pattern
from src.db.session import AsyncSessionLocal
from src.ingestion.nba_stats_ingester import CURRENT_SEASON
from src.models.team import Team
from src.models.team_defensive_stats import TeamDefensiveStats
from src.utils.rate_limiter import nba_limiter

logger = logging.getLogger(__name__)


async def ingest_defensive_stats() -> None:
    """Refresh season-to-date opponent stats allowed per team."""
    logger.info("ingest_defensive_stats: starting for season %s", CURRENT_SEASON)

    opp_rows, adv_rows = await asyncio.gather(
        _fetch_opponent_stats(),
        _fetch_advanced_stats(),
    )

    # Build def_rating lookup: nba_team_id → def_rating
    def_rating_map: dict[int, float] = {}
    for row in adv_rows:
        tid = row.get("TEAM_ID")
        dr = row.get("DEF_RATING")
        if tid and dr is not None:
            def_rating_map[tid] = float(dr)

    async with AsyncSessionLocal() as session:
        team_result = await session.execute(select(Team.nba_id, Team.id))
        team_map: dict[int, int] = {row.nba_id: row.id for row in team_result}

        upserted = skipped = 0
        for row in opp_rows:
            nba_team_id = row.get("TEAM_ID")
            internal_id = team_map.get(nba_team_id)
            if not internal_id:
                skipped += 1
                continue

            stmt = (
                pg_insert(TeamDefensiveStats)
                .values(
                    team_id=internal_id,
                    season=CURRENT_SEASON,
                    games_played=_int(row.get("GP")),
                    opp_pts_pg=_float(row.get("OPP_PTS")),
                    opp_reb_pg=_float(row.get("OPP_REB")),
                    opp_ast_pg=_float(row.get("OPP_AST")),
                    opp_fg3m_pg=_float(row.get("OPP_FG3M")),
                    opp_stl_pg=_float(row.get("OPP_STL")),
                    opp_blk_pg=_float(row.get("OPP_BLK")),
                    opp_tov_pg=_float(row.get("OPP_TOV")),
                    def_rating=def_rating_map.get(nba_team_id),
                )
                .on_conflict_do_update(
                    constraint="uq_team_defensive_stats_team_id_season",
                    set_={
                        "games_played": _int(row.get("GP")),
                        "opp_pts_pg": _float(row.get("OPP_PTS")),
                        "opp_reb_pg": _float(row.get("OPP_REB")),
                        "opp_ast_pg": _float(row.get("OPP_AST")),
                        "opp_fg3m_pg": _float(row.get("OPP_FG3M")),
                        "opp_stl_pg": _float(row.get("OPP_STL")),
                        "opp_blk_pg": _float(row.get("OPP_BLK")),
                        "opp_tov_pg": _float(row.get("OPP_TOV")),
                        "def_rating": def_rating_map.get(nba_team_id),
                    },
                )
            )
            await session.execute(stmt)
            upserted += 1

        await session.commit()

    await cache_delete_pattern(PATTERN_PROJECTIONS_ALL)
    logger.info(
        "ingest_defensive_stats: upserted %d teams, skipped %d", upserted, skipped
    )


async def _fetch_opponent_stats() -> list[dict]:
    from nba_api.stats.endpoints import LeagueDashTeamStats

    await nba_limiter.acquire()
    endpoint = await asyncio.get_event_loop().run_in_executor(
        None,
        partial(
            LeagueDashTeamStats,
            season=CURRENT_SEASON,
            measure_type_simple="Opponent",
            per_mode_simple="PerGame",
        ),
    )
    return endpoint.get_normalized_dict()["LeagueDashTeamStats"]


async def _fetch_advanced_stats() -> list[dict]:
    from nba_api.stats.endpoints import LeagueDashTeamStats

    await nba_limiter.acquire()
    endpoint = await asyncio.get_event_loop().run_in_executor(
        None,
        partial(
            LeagueDashTeamStats,
            season=CURRENT_SEASON,
            measure_type_simple="Advanced",
            per_mode_simple="PerGame",
        ),
    )
    return endpoint.get_normalized_dict()["LeagueDashTeamStats"]


def _int(val) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None
