"""
NBA stats ingestion using nba_api (stats.nba.com / live.nba.com).

All nba_api calls are synchronous — we run them in a thread pool executor
to avoid blocking the event loop.

Rate limiter: 0.6s between requests (see src/utils/rate_limiter.py).

Endpoints used:
  nba_api.live.nba.endpoints.scoreboard  → today's live schedule + scores
  nba_api.stats.endpoints.LeagueGameLog  → all box scores for a date range (1 request)
  nba_api.stats.endpoints.LeagueDashPlayerStats → all season averages (1 request)
"""

import asyncio
import logging
from datetime import date, timedelta
from functools import partial

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.cache.keys import (
    PATTERN_PLAYER_GAMELOGS_ALL,
    PATTERN_PLAYER_STATS_ALL,
    PATTERN_PROJECTIONS_ALL,
    games_today,
)
from src.cache.redis_client import cache_delete, cache_delete_pattern
from src.db.session import AsyncSessionLocal
from src.models.game import Game
from src.models.game_log import PlayerGameLog
from src.models.player import Player
from src.models.season_averages import PlayerSeasonAverages
from src.models.team import Team
from src.utils.rate_limiter import nba_limiter

logger = logging.getLogger(__name__)

CURRENT_SEASON = "2025-26"


# ── Today's schedule ──────────────────────────────────────────────────────────

async def ingest_todays_games() -> None:
    """Fetch today's NBA schedule and scores, upsert into the games table."""
    logger.info("ingest_todays_games: fetching live scoreboard")

    from nba_api.live.nba.endpoints import scoreboard as sb_module

    await nba_limiter.acquire()
    board = await asyncio.get_event_loop().run_in_executor(
        None, sb_module.ScoreBoard
    )
    games_raw = board.games.get_dict()
    logger.info("ingest_todays_games: found %d games", len(games_raw))

    async with AsyncSessionLocal() as session:
        # Build nba_team_id → internal id map
        team_result = await session.execute(select(Team.nba_id, Team.id))
        team_map: dict[int, int] = {row.nba_id: row.id for row in team_result}

        upserted = 0
        for g in games_raw:
            home_nba_id = g["homeTeam"]["teamId"]
            away_nba_id = g["awayTeam"]["teamId"]

            home_id = team_map.get(home_nba_id)
            away_id = team_map.get(away_nba_id)

            if not home_id or not away_id:
                logger.warning(
                    "ingest_todays_games: unknown team(s) for game %s "
                    "(home nba_id=%s, away nba_id=%s) — run ingest_roster_updates first",
                    g["gameId"],
                    home_nba_id,
                    away_nba_id,
                )
                continue

            home_score = g["homeTeam"].get("score") or None
            away_score = g["awayTeam"].get("score") or None
            # score comes back as int 0 during pregame — treat 0 as None
            if home_score == 0 and away_score == 0:
                home_score, away_score = None, None

            stmt = (
                pg_insert(Game)
                .values(
                    nba_game_id=g["gameId"],
                    game_date=date.today(),
                    home_team_id=home_id,
                    away_team_id=away_id,
                    status=g.get("gameStatusText", "scheduled"),
                    home_score=home_score,
                    away_score=away_score,
                    season=CURRENT_SEASON,
                    season_type=_season_type(g.get("gameSubtype", "")),
                )
                .on_conflict_do_update(
                    index_elements=["nba_game_id"],
                    set_={
                        "status": g.get("gameStatusText", "scheduled"),
                        "home_score": home_score,
                        "away_score": away_score,
                    },
                )
            )
            await session.execute(stmt)
            upserted += 1

        await session.commit()

    await cache_delete(games_today())
    await cache_delete_pattern(PATTERN_PROJECTIONS_ALL)
    logger.info("ingest_todays_games: upserted %d games", upserted)


# ── Game logs ─────────────────────────────────────────────────────────────────

async def ingest_game_logs() -> None:
    """
    Pull box scores for the last completed game day and upsert into player_game_logs.

    Uses LeagueGameLog which returns every player's line for every game
    in the date range — much more efficient than per-player requests.
    """
    yesterday = date.today() - timedelta(days=1)
    date_str = yesterday.strftime("%m/%d/%Y")
    logger.info("ingest_game_logs: fetching box scores for %s", date_str)

    from nba_api.stats.endpoints import LeagueGameLog

    await nba_limiter.acquire()
    endpoint = await asyncio.get_event_loop().run_in_executor(
        None,
        partial(
            LeagueGameLog,
            season=CURRENT_SEASON,
            date_from_nullable=date_str,
            date_to_nullable=date_str,
            player_or_team_abbreviation="P",  # player-level rows
        ),
    )
    rows = endpoint.get_normalized_dict()["LeagueGameLog"]
    logger.info("ingest_game_logs: got %d player-game rows", len(rows))

    if not rows:
        logger.info("ingest_game_logs: no games on %s", yesterday)
        return

    async with AsyncSessionLocal() as session:
        # Map nba_game_id → internal game id
        nba_game_ids = {r["GAME_ID"] for r in rows}
        game_result = await session.execute(
            select(Game.nba_game_id, Game.id).where(
                Game.nba_game_id.in_(nba_game_ids)
            )
        )
        game_map: dict[str, int] = {row.nba_game_id: row.id for row in game_result}

        # Map nba player id → internal player id
        nba_player_ids = {r["PLAYER_ID"] for r in rows}
        player_result = await session.execute(
            select(Player.nba_id, Player.id).where(
                Player.nba_id.in_(nba_player_ids)
            )
        )
        player_map: dict[int, int] = {row.nba_id: row.id for row in player_result}

        upserted = skipped = 0
        for r in rows:
            internal_game_id = game_map.get(r["GAME_ID"])
            internal_player_id = player_map.get(r["PLAYER_ID"])

            if not internal_game_id or not internal_player_id:
                skipped += 1
                continue

            stmt = (
                pg_insert(PlayerGameLog)
                .values(
                    player_id=internal_player_id,
                    game_id=internal_game_id,
                    minutes=str(r.get("MIN")) if r.get("MIN") is not None else None,
                    points=_int(r.get("PTS")),
                    rebounds=_int(r.get("REB")),
                    assists=_int(r.get("AST")),
                    steals=_int(r.get("STL")),
                    blocks=_int(r.get("BLK")),
                    turnovers=_int(r.get("TOV")),
                    fg_made=_int(r.get("FGM")),
                    fg_attempted=_int(r.get("FGA")),
                    fg3_made=_int(r.get("FG3M")),
                    fg3_attempted=_int(r.get("FG3A")),
                    ft_made=_int(r.get("FTM")),
                    ft_attempted=_int(r.get("FTA")),
                    plus_minus=_int(r.get("PLUS_MINUS")),
                )
                .on_conflict_do_update(
                    constraint="uq_player_game_logs_player_id_game_id",
                    set_={
                        "minutes": str(r.get("MIN")) if r.get("MIN") is not None else None,
                        "points": _int(r.get("PTS")),
                        "rebounds": _int(r.get("REB")),
                        "assists": _int(r.get("AST")),
                        "steals": _int(r.get("STL")),
                        "blocks": _int(r.get("BLK")),
                        "turnovers": _int(r.get("TOV")),
                        "fg_made": _int(r.get("FGM")),
                        "fg_attempted": _int(r.get("FGA")),
                        "fg3_made": _int(r.get("FG3M")),
                        "fg3_attempted": _int(r.get("FG3A")),
                        "ft_made": _int(r.get("FTM")),
                        "ft_attempted": _int(r.get("FTA")),
                        "plus_minus": _int(r.get("PLUS_MINUS")),
                    },
                )
            )
            await session.execute(stmt)
            upserted += 1

        await session.commit()

    await cache_delete_pattern(PATTERN_PLAYER_GAMELOGS_ALL)
    await cache_delete_pattern(PATTERN_PLAYER_STATS_ALL)
    await cache_delete_pattern(PATTERN_PROJECTIONS_ALL)
    logger.info(
        "ingest_game_logs: upserted %d rows, skipped %d (unknown game/player)",
        upserted,
        skipped,
    )


# ── Season averages ───────────────────────────────────────────────────────────

async def ingest_season_averages() -> None:
    """
    Refresh season averages for all active players via LeagueDashPlayerStats.
    One API call covers every player — very efficient.
    """
    logger.info("ingest_season_averages: fetching for season %s", CURRENT_SEASON)

    from nba_api.stats.endpoints import LeagueDashPlayerStats

    await nba_limiter.acquire()
    endpoint = await asyncio.get_event_loop().run_in_executor(
        None,
        partial(
            LeagueDashPlayerStats,
            season=CURRENT_SEASON,
            per_mode_detailed="PerGame",
            measure_type_detailed_defense="Base",
        ),
    )
    rows = endpoint.get_normalized_dict()["LeagueDashPlayerStats"]
    logger.info("ingest_season_averages: got %d player rows", len(rows))

    async with AsyncSessionLocal() as session:
        nba_player_ids = {r["PLAYER_ID"] for r in rows}
        player_result = await session.execute(
            select(Player.nba_id, Player.id).where(
                Player.nba_id.in_(nba_player_ids)
            )
        )
        player_map: dict[int, int] = {row.nba_id: row.id for row in player_result}

        upserted = skipped = 0
        for r in rows:
            internal_player_id = player_map.get(r["PLAYER_ID"])
            if not internal_player_id:
                skipped += 1
                continue

            stmt = (
                pg_insert(PlayerSeasonAverages)
                .values(
                    player_id=internal_player_id,
                    season=CURRENT_SEASON,
                    games_played=_int(r.get("GP")),
                    mpg=_float(r.get("MIN")),
                    ppg=_float(r.get("PTS")),
                    rpg=_float(r.get("REB")),
                    apg=_float(r.get("AST")),
                    spg=_float(r.get("STL")),
                    bpg=_float(r.get("BLK")),
                    fg_pct=_float(r.get("FG_PCT")),
                    fg3_pct=_float(r.get("FG3_PCT")),
                    ft_pct=_float(r.get("FT_PCT")),
                )
                .on_conflict_do_update(
                    constraint="uq_player_season_averages_player_id_season",
                    set_={
                        "games_played": _int(r.get("GP")),
                        "mpg": _float(r.get("MIN")),
                        "ppg": _float(r.get("PTS")),
                        "rpg": _float(r.get("REB")),
                        "apg": _float(r.get("AST")),
                        "spg": _float(r.get("STL")),
                        "bpg": _float(r.get("BLK")),
                        "fg_pct": _float(r.get("FG_PCT")),
                        "fg3_pct": _float(r.get("FG3_PCT")),
                        "ft_pct": _float(r.get("FT_PCT")),
                    },
                )
            )
            await session.execute(stmt)
            upserted += 1

        await session.commit()

    await cache_delete_pattern(PATTERN_PLAYER_STATS_ALL)
    logger.info(
        "ingest_season_averages: upserted %d, skipped %d", upserted, skipped
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _season_type(subtype: str) -> str:
    subtype = (subtype or "").lower()
    if "playoff" in subtype:
        return "Playoffs"
    if "preseason" in subtype or "pre-season" in subtype:
        return "Pre Season"
    return "Regular Season"
