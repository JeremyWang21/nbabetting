import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.cache.redis_client import close_redis
from src.db.session import engine
from src.ingestion.scheduler import shutdown_scheduler, start_scheduler
from src.routes import admin, custom_lines, games, injuries, players, projections, props

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting NBA Betting Dashboard")
    await start_scheduler()
    yield
    logger.info("Shutting down")
    await shutdown_scheduler()
    await engine.dispose()
    await close_redis()


app = FastAPI(
    title="NBA Betting Dashboard",
    description="Player props, odds comparison, and NBA stats in one place.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(games.router, prefix="/api/v1")
app.include_router(players.router, prefix="/api/v1")
app.include_router(projections.router, prefix="/api/v1")
app.include_router(custom_lines.router, prefix="/api/v1")
app.include_router(injuries.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")

_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static), name="static")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(_static / "index.html")
