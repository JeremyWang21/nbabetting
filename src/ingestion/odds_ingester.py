"""
Odds ingestion from The Odds API (https://the-odds-api.com).

Fetches NBA player prop lines every N minutes (default: 3 min).
Writes a PropSnapshot row per (player, game, market, bookmaker) fetch.
Busts the relevant Redis cache keys after each successful write.

Tracked prop markets:
  - player_points
  - player_rebounds
  - player_assists
  - player_threes    (3-pointers made)
  - player_blocks
  - player_steals
  - player_turnovers

Sprint 3 implementation checklist:
  [ ] TODO Sprint 3: resolve The Odds API event IDs to internal game IDs
  [ ] TODO Sprint 3: resolve player names to internal player IDs
  [ ] TODO Sprint 3: write PropSnapshot rows
  [ ] TODO Sprint 3: bust Redis cache keys after write
"""

import logging

logger = logging.getLogger(__name__)

PROP_MARKETS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_blocks",
    "player_steals",
    "player_turnovers",
]

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "basketball_nba"


async def ingest_live_odds() -> None:
    """
    Fetch current NBA player prop lines from The Odds API and persist them.
    Called every ODDS_POLL_INTERVAL_SECONDS by the scheduler.
    """
    logger.info("ingest_live_odds: starting")
    # TODO Sprint 3: implement
    # 1. GET /v4/sports/basketball_nba/events  → list of today's event IDs
    # 2. For each event:
    #    GET /v4/sports/basketball_nba/events/{eventId}/odds
    #      ?apiKey=...&markets=player_points,player_rebounds,...&oddsFormat=american
    # 3. Parse bookmakers[].markets[].outcomes[]
    # 4. Upsert PropSnapshot rows
    # 5. Bust Redis: await cache_delete_pattern(f"odds:game:{game_id}:*")
    #               await cache_delete("props:best_lines:today")
    logger.info("ingest_live_odds: done (stub)")
