"""
Bootstrap script — run once to seed the database with initial data.

Usage (from repo root, with docker-compose running):
    docker-compose exec app python scripts/bootstrap.py

Or locally (with DATABASE_URL set):
    python scripts/bootstrap.py

Order matters:
  1. teams   — players.team_id references team internal IDs
  2. players — game_logs and season_averages reference player IDs
  3. season_averages — can run after players
  4. (game_logs are populated nightly via ingest_game_logs)
"""

import asyncio
import logging
import sys
import os

# Make sure src/ is on the path when running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger("bootstrap")


async def main() -> None:
    from src.ingestion.roster_ingester import ingest_roster_updates
    from src.ingestion.nba_stats_ingester import ingest_season_averages, ingest_todays_games
    from src.ingestion.defensive_stats_ingester import ingest_defensive_stats

    logger.info("=== Bootstrap starting ===")

    logger.info("Step 1/4: syncing teams + players (roster)")
    await ingest_roster_updates()

    logger.info("Step 2/4: fetching today's games")
    await ingest_todays_games()

    logger.info("Step 3/4: fetching season averages (all active players)")
    await ingest_season_averages()

    logger.info("Step 4/4: fetching team defensive stats (matchup data)")
    await ingest_defensive_stats()

    logger.info("=== Bootstrap complete ===")
    logger.info("You can now call:")
    logger.info("  GET /api/v1/games/today")
    logger.info("  GET /api/v1/players/search?q=<name>")
    logger.info("  GET /api/v1/players/{id}/stats")
    logger.info("  GET /api/v1/players/{id}/gamelogs")
    logger.info("  GET /api/v1/projections/today  (matchup-adjusted)")


if __name__ == "__main__":
    asyncio.run(main())
