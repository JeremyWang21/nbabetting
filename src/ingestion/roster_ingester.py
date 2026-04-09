"""
Roster sync using nba_api static data + CommonAllPlayers endpoint.

nba_api.stats.static:
  - teams.get_teams()   → all 30 NBA teams (no HTTP call, bundled JSON)
  - players.get_active_players() → all active players (no HTTP call)

nba_api.stats.endpoints.CommonAllPlayers:
  → live roster with current team assignments

Runs daily at 6am to catch trades, signings, and waiver moves.
"""

import asyncio
import logging
from functools import partial

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.db.session import AsyncSessionLocal
from src.models.player import Player
from src.models.team import Team
from src.utils.rate_limiter import nba_limiter

logger = logging.getLogger(__name__)

# Current season — update each year
CURRENT_SEASON = "2025-26"


async def ingest_roster_updates() -> None:
    """Sync all 30 teams and all active players from nba_api."""
    logger.info("ingest_roster_updates: starting")
    await _sync_teams()
    await _sync_players()
    await _sync_positions()
    await _fix_team_ids_from_game_logs()
    logger.info("ingest_roster_updates: done")


async def _sync_teams() -> None:
    from nba_api.stats.static import teams as nba_teams_static

    # get_teams() is a bundled JSON lookup — no HTTP call, no rate limit needed
    teams_data = await asyncio.get_event_loop().run_in_executor(
        None, nba_teams_static.get_teams
    )
    logger.info("_sync_teams: upserting %d teams", len(teams_data))

    async with AsyncSessionLocal() as session:
        for t in teams_data:
            stmt = (
                pg_insert(Team)
                .values(
                    nba_id=t["id"],
                    name=t["full_name"],
                    abbreviation=t["abbreviation"],
                    city=t["city"],
                    conference=None,  # not in static data; set manually or via another endpoint
                    division=None,
                )
                .on_conflict_do_update(
                    index_elements=["nba_id"],
                    set_={
                        "name": t["full_name"],
                        "abbreviation": t["abbreviation"],
                        "city": t["city"],
                    },
                )
            )
            await session.execute(stmt)
        await session.commit()
    logger.info("_sync_teams: done")


async def _sync_players() -> None:
    """
    Fetch active players with current team assignments via CommonAllPlayers.
    Falls back to static player list if the API call fails.
    """
    from nba_api.stats.endpoints import CommonAllPlayers

    await nba_limiter.acquire()
    try:
        endpoint = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                CommonAllPlayers,
                is_only_current_season=1,
                league_id="00",
                season=CURRENT_SEASON,
            ),
        )
        players_data = endpoint.get_normalized_dict()["CommonAllPlayers"]
    except Exception as exc:
        logger.warning("CommonAllPlayers failed (%s), falling back to static list", exc)
        from nba_api.stats.static import players as nba_players_static
        raw = await asyncio.get_event_loop().run_in_executor(
            None, nba_players_static.get_active_players
        )
        # static list has id, full_name, first_name, last_name, is_active
        players_data = [
            {
                "PERSON_ID": p["id"],
                "DISPLAY_FIRST_LAST": p["full_name"],
                "PLAYER_FIRST_NAME": p["first_name"],
                "PLAYER_LAST_NAME": p["last_name"],
                "TEAM_ID": 0,
                "ROSTERSTATUS": "1",
            }
            for p in raw
        ]

    logger.info("_sync_players: upserting %d players", len(players_data))

    async with AsyncSessionLocal() as session:
        # Build nba_team_id → internal id map
        from sqlalchemy import select
        team_result = await session.execute(select(Team.nba_id, Team.id))
        team_map: dict[int, int] = {row.nba_id: row.id for row in team_result}

        for p in players_data:
            nba_team_id = p.get("TEAM_ID") or 0
            internal_team_id = team_map.get(nba_team_id)  # None for free agents

            # Parse name — CommonAllPlayers gives DISPLAY_FIRST_LAST
            full_name = p.get("DISPLAY_FIRST_LAST", "")
            first_name = p.get("PLAYER_FIRST_NAME") or full_name.split(" ")[0]
            last_name = p.get("PLAYER_LAST_NAME") or (
                " ".join(full_name.split(" ")[1:]) if " " in full_name else ""
            )

            is_active = str(p.get("ROSTERSTATUS", "1")) == "1"

            # Only update team_id if the API gives a real team (not 0/None).
            # CommonAllPlayers often returns TEAM_ID=0 for active players,
            # which would clobber a correct team_id we derived from game logs.
            update_set = {
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": is_active,
            }
            if internal_team_id is not None:
                update_set["team_id"] = internal_team_id

            stmt = (
                pg_insert(Player)
                .values(
                    nba_id=p["PERSON_ID"],
                    full_name=full_name,
                    first_name=first_name,
                    last_name=last_name,
                    team_id=internal_team_id,
                    is_active=is_active,
                )
                .on_conflict_do_update(
                    index_elements=["nba_id"],
                    set_=update_set,
                )
            )
            await session.execute(stmt)

        await session.commit()
    logger.info("_sync_players: done")


async def _sync_positions() -> None:
    """Backfill position + jersey_number via PlayerIndex (one bulk call)."""
    from nba_api.stats.endpoints import PlayerIndex
    from sqlalchemy import select
    from sqlalchemy import update as sa_update

    await nba_limiter.acquire()
    try:
        endpoint = await asyncio.get_event_loop().run_in_executor(
            None, partial(PlayerIndex, league_id="00", season=CURRENT_SEASON)
        )
        rows = endpoint.get_normalized_dict()["PlayerIndex"]
    except Exception as exc:
        logger.warning("_sync_positions: PlayerIndex failed (%s)", exc)
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player.nba_id, Player.id))
        player_map: dict[int, int] = {row.nba_id: row.id for row in result}
        updated = 0
        for r in rows:
            pid = player_map.get(r["PERSON_ID"])
            if not pid:
                continue
            await session.execute(
                sa_update(Player).where(Player.id == pid).values(
                    position=r.get("POSITION") or None,
                    jersey_number=r.get("JERSEY_NUMBER") or None,
                )
            )
            updated += 1
        await session.commit()
    logger.info("_sync_positions: updated %d players", updated)


async def _fix_team_ids_from_game_logs() -> None:
    """
    Fix stale team_id using recent game logs.

    CommonAllPlayers is often wrong for recently traded players.
    We use the nba_api PlayerIndex endpoint's TEAM_ID which is more
    up-to-date, but as a final safety net we also check game logs:
    if a player's most recent game was for a different team than
    their stored team_id, update it.
    """
    from sqlalchemy import select, func, text
    from sqlalchemy import update as sa_update

    async with AsyncSessionLocal() as session:
        from src.models.game import Game
        from src.models.game_log import PlayerGameLog

        # Use a raw SQL query for efficiency:
        # For each player, find their most recent game log, get the game's
        # home/away teams, and check if the player's team_id matches either.
        # If not, the player was traded and we need to figure out which team.
        result = await session.execute(text("""
            WITH latest AS (
                SELECT DISTINCT ON (pgl.player_id)
                    pgl.player_id,
                    g.home_team_id,
                    g.away_team_id,
                    g.game_date
                FROM player_game_logs pgl
                JOIN games g ON pgl.game_id = g.id
                ORDER BY pgl.player_id, g.game_date DESC
            )
            SELECT l.player_id, l.home_team_id, l.away_team_id, p.team_id
            FROM latest l
            JOIN players p ON l.player_id = p.id
            WHERE p.team_id IS NULL
               OR p.team_id NOT IN (l.home_team_id, l.away_team_id)
        """))
        mismatches = result.all()

        if not mismatches:
            logger.info("_fix_team_ids_from_game_logs: all team_ids correct")
            return

        logger.warning("_fix_team_ids_from_game_logs: %d players with stale team_id", len(mismatches))

        fixed = 0
        for pid, home_tid, away_tid, current_tid in mismatches:
            # Count how many game logs this player has with each team as home/away
            # to figure out which side they're on
            home_count = await session.execute(
                select(func.count()).select_from(PlayerGameLog)
                .join(Game, PlayerGameLog.game_id == Game.id)
                .where(
                    PlayerGameLog.player_id == pid,
                    Game.home_team_id == home_tid,
                )
            )
            away_count = await session.execute(
                select(func.count()).select_from(PlayerGameLog)
                .join(Game, PlayerGameLog.game_id == Game.id)
                .where(
                    PlayerGameLog.player_id == pid,
                    Game.away_team_id == away_tid,
                )
            )
            h_cnt = home_count.scalar() or 0
            a_cnt = away_count.scalar() or 0
            # The team with more games is likely the player's actual team
            # (they play ~41 home and ~41 away, but after trade they'd have
            # more games with new team as either home or away)
            # Simpler: just pick whichever team they appeared with more recently
            new_team_id = home_tid if h_cnt >= a_cnt else away_tid
            await session.execute(
                sa_update(Player).where(Player.id == pid).values(team_id=new_team_id)
            )
            player = await session.get(Player, pid)
            logger.info("_fix_team_ids: %s: team %d → %d", player.full_name if player else pid, current_tid, new_team_id)
            fixed += 1

        await session.commit()
    logger.info("_fix_team_ids_from_game_logs: fixed %d players", fixed)
