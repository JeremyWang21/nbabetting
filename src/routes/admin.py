"""
Admin / debug endpoints.
Not authenticated — personal use only. Do not expose publicly.
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.cache.redis_client import cache_delete_pattern, get_redis
from src.config.settings import settings
from src.ingestion.nba_stats_ingester import ingest_todays_games
from src.ingestion.scheduler import get_scheduler


def _require_secret(x_admin_secret: str = Header("")) -> None:
    if settings.admin_secret and x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

router = APIRouter(prefix="/admin", tags=["admin"])


class CacheStatusResponse(BaseModel):
    total_keys: int
    keys_by_prefix: dict[str, int]


class SchedulerStatusResponse(BaseModel):
    running: bool
    jobs: list[dict]


@router.get("/cache", response_model=CacheStatusResponse)
async def cache_status():
    """Show how many Redis keys exist per prefix."""
    client = get_redis()
    all_keys: list[str] = await client.keys("*")

    by_prefix: dict[str, int] = {}
    for key in all_keys:
        prefix = key.split(":")[0]
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1

    return CacheStatusResponse(total_keys=len(all_keys), keys_by_prefix=by_prefix)


@router.delete("/cache", status_code=204)
async def flush_cache(pattern: str = "*"):
    """
    Delete Redis keys matching a glob pattern.
    Default flushes everything. Examples:
      ?pattern=projections:*   flush only projections
      ?pattern=player:*        flush player stats + gamelogs
      ?pattern=*               flush all (full reset)
    """
    await cache_delete_pattern(pattern)


@router.get("/scheduler", response_model=SchedulerStatusResponse)
async def scheduler_status():
    """Show all registered scheduler jobs and their next run times."""
    scheduler = get_scheduler()
    jobs = [
        {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
        }
        for job in scheduler.get_jobs()
    ]
    return SchedulerStatusResponse(running=scheduler.running, jobs=jobs)


@router.post("/refresh-today", status_code=200)
async def refresh_today(x_admin_secret: str = Header("")):
    """Flush today's game cache and re-ingest from nba_api."""
    _require_secret(x_admin_secret)
    await cache_delete_pattern("games:*")
    await ingest_todays_games()
    return {"ok": True}


@router.post("/scheduler/{job_id}/run", status_code=202)
async def trigger_job(job_id: str):
    """Manually trigger a scheduler job by ID (runs immediately, async)."""
    scheduler = get_scheduler()
    job = scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    scheduler.modify_job(job_id, next_run_time=__import__("datetime").datetime.now())
    return {"triggered": job_id}
