import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.ingestion.defensive_stats_ingester import ingest_defensive_stats
from src.ingestion.injury_ingester import ingest_injury_report
from src.ingestion.nba_stats_ingester import (
    ingest_game_logs,
    ingest_season_averages,
    ingest_todays_games,
)
from src.ingestion.roster_ingester import ingest_roster_updates

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="America/New_York")

    # ── Live updates (during game hours) ──────────────────────────────────────

    scheduler.add_job(
        ingest_todays_games,
        IntervalTrigger(minutes=30),
        id="ingest_todays_games",
        name="Refresh today's schedule and scores",
        replace_existing=True,
        misfire_grace_time=120,
    )

    scheduler.add_job(
        ingest_injury_report,
        IntervalTrigger(minutes=15),
        id="ingest_injury_report",
        name="Refresh injury status (Tank01 + NBA PDF)",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── Nightly batch (runs early morning after games finish) ─────────────────

    scheduler.add_job(
        ingest_game_logs,
        CronTrigger(hour=4, minute=0),
        id="ingest_game_logs",
        name="Pull last night's box scores",
        replace_existing=True,
    )

    scheduler.add_job(
        ingest_season_averages,
        CronTrigger(hour=4, minute=30),
        id="ingest_season_averages",
        name="Refresh season averages (all active players)",
        replace_existing=True,
    )

    scheduler.add_job(
        ingest_defensive_stats,
        CronTrigger(hour=5, minute=0),
        id="ingest_defensive_stats",
        name="Refresh opponent defensive stats (matchup adjustment data)",
        replace_existing=True,
    )

    scheduler.add_job(
        ingest_roster_updates,
        CronTrigger(hour=6, minute=0),
        id="ingest_roster_updates",
        name="Sync player/team rosters (handles trades, signings)",
        replace_existing=True,
    )

    return scheduler


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
    return _scheduler


async def start_scheduler() -> None:
    scheduler = get_scheduler()
    scheduler.start()
    logger.info(
        "Scheduler started — %d jobs registered: %s",
        len(scheduler.get_jobs()),
        [j.id for j in scheduler.get_jobs()],
    )


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
