"""
Injury report ingestion from two sources:

  1. Tank01 RapidAPI (primary)
     GET /getNBATeamRoster?teamAbv={abbr}
     Each player object has an `injury` field with designation + description.
     Designations: "Out", "Game Time Decision", "Questionable", "Probable", ""

  2. NBA Official Injury Report PDF (supplement, best-effort)
     Published ~5pm ET on game days at a URL that changes daily.
     Parsed with pdfplumber to extract structured designations.

Runs every 15 minutes. Busts the injuries:today Redis key after each write.
"""

import asyncio
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.cache.keys import TTL_INJURIES, injuries_today
from src.cache.redis_client import cache_delete, cache_set
from src.config.settings import settings
from src.db.session import AsyncSessionLocal
from src.models.game import Game
from src.models.injury import InjuryReport
from src.models.player import Player
from src.models.team import Team
from src.schemas.injury import InjuryListResponse, InjuryReportResponse
from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)

TANK01_BASE = "https://tank01-fantasy-stats.p.rapidapi.com"

# Map Tank01 designation strings → our canonical status values
DESIGNATION_MAP = {
    "out": "OUT",
    "game time decision": "GTD",
    "questionable": "QUESTIONABLE",
    "probable": "PROBABLE",
    "": "AVAILABLE",
}


async def ingest_injury_report() -> None:
    """
    Fetch injury status for all active players from Tank01.
    Runs every 15 minutes via the scheduler.
    """
    if not settings.tank01_api_key:
        logger.warning("ingest_injury_report: TANK01_API_KEY not set — skipping")
        return

    logger.info("ingest_injury_report: starting")

    async with AsyncSessionLocal() as session:
        # Get all teams so we can iterate by abbreviation
        team_result = await session.execute(
            select(Team.id, Team.abbreviation, Team.nba_id)
        )
        teams = team_result.all()

        # Build player lookup: nba_id → internal id
        player_result = await session.execute(
            select(Player.nba_id, Player.id).where(Player.is_active.is_(True))
        )
        player_map: dict[int, int] = {row.nba_id: row.id for row in player_result}

        # Find today's game_ids for linking injury reports to games
        today = date.today()
        game_result = await session.execute(
            select(Game.id, Game.home_team_id, Game.away_team_id)
            .where(Game.game_date == today)
        )
        today_games = game_result.all()

        # Map team internal id → today's game id
        team_to_game: dict[int, int] = {}
        for g in today_games:
            team_to_game[g.home_team_id] = g.id
            team_to_game[g.away_team_id] = g.id

    # Fetch rosters with injury data from Tank01 (one request per team)
    injured_players = await _fetch_all_team_rosters(
        [t.abbreviation for t in teams]
    )

    if not injured_players:
        logger.info("ingest_injury_report: no injury data returned")
        return

    now = datetime.now(timezone.utc)
    inserted = skipped = 0

    async with AsyncSessionLocal() as session:
        # Rebuild team lookup inside this session
        team_result = await session.execute(select(Team.id, Team.abbreviation))
        team_abbr_map: dict[str, int] = {row.abbreviation: row.id for row in team_result}

        player_result = await session.execute(
            select(Player.nba_id, Player.id).where(Player.is_active.is_(True))
        )
        player_map = {row.nba_id: row.id for row in player_result}

        for entry in injured_players:
            internal_player_id = player_map.get(entry["player_nba_id"])
            if not internal_player_id:
                skipped += 1
                continue

            team_internal_id = team_abbr_map.get(entry["team_abbr"])
            game_id = team_to_game.get(team_internal_id) if team_internal_id else None

            # Insert a new snapshot row (historical record of status changes)
            stmt = pg_insert(InjuryReport).values(
                player_id=internal_player_id,
                game_id=game_id,
                status=entry["status"],
                injury_description=entry.get("description"),
                return_date_estimate=None,
                source="tank01",
                reported_at=now,
            )
            await session.execute(stmt)
            inserted += 1

        await session.commit()

    await cache_delete(injuries_today())
    logger.info(
        "ingest_injury_report: inserted %d rows, skipped %d (unknown player)",
        inserted,
        skipped,
    )


async def _fetch_all_team_rosters(
    team_abbreviations: list[str],
) -> list[dict]:
    """
    Fetch Tank01 rosters for all teams concurrently (batched to avoid
    hammering the API — 5 teams at a time).
    Returns a flat list of injury entries for players with non-empty status.
    """
    headers = {
        "x-rapidapi-key": settings.tank01_api_key,
        "x-rapidapi-host": "tank01-fantasy-stats.p.rapidapi.com",
    }

    results: list[dict] = []
    batch_size = 5

    async with get_http_client(timeout=15.0, retries=2) as client:
        for i in range(0, len(team_abbreviations), batch_size):
            batch = team_abbreviations[i : i + batch_size]
            tasks = [
                _fetch_team_roster(client, headers, abbr) for abbr in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for abbr, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.warning(
                        "_fetch_all_team_rosters: failed for %s — %s", abbr, result
                    )
                    continue
                results.extend(result)

            # Brief pause between batches to respect rate limits
            if i + batch_size < len(team_abbreviations):
                await asyncio.sleep(1.0)

    return results


async def _fetch_team_roster(client, headers: dict, team_abbr: str) -> list[dict]:
    """Fetch one team's roster and extract injury entries."""
    resp = await client.get(
        f"{TANK01_BASE}/getNBATeamRoster",
        headers=headers,
        params={"teamAbv": team_abbr, "getStats": "false"},
    )
    resp.raise_for_status()
    data = resp.json()

    roster = data.get("body", {}).get("roster", [])
    if not roster:
        return []

    entries = []
    for player in roster:
        injury = player.get("injury") or {}
        raw_designation = (injury.get("designation") or "").strip().lower()

        # Skip players with no injury designation (they're available)
        if not raw_designation:
            continue

        status = DESIGNATION_MAP.get(raw_designation, raw_designation.upper())

        try:
            player_nba_id = int(player.get("playerID") or 0)
        except (ValueError, TypeError):
            continue

        if not player_nba_id:
            continue

        entries.append(
            {
                "player_nba_id": player_nba_id,
                "team_abbr": team_abbr,
                "status": status,
                "description": injury.get("description") or injury.get("injDesc"),
            }
        )

    return entries
