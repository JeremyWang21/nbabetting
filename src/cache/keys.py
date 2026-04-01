"""
Centralized Redis key patterns and TTLs.

All cache keys are defined here so ingesters and services
stay in sync when busting.
"""

# ── TTLs (seconds) ────────────────────────────────────────────────────────────
TTL_GAMES_TODAY = 1800        # 30 min — refreshed when ingest_todays_games runs
TTL_PLAYER_STATS = 21600      # 6 hours — refreshed nightly at 4:30am
TTL_PLAYER_GAMELOGS = 21600   # 6 hours — refreshed nightly at 4am
TTL_PROJECTIONS = 1800        # 30 min — refresh after game logs or defensive stats
TTL_INJURIES = 900            # 15 min — refreshed by ingest_injury_report


# ── Key builders ──────────────────────────────────────────────────────────────

def games_today() -> str:
    return "games:today"


def player_stats(player_id: int) -> str:
    return f"player:stats:{player_id}"


def player_gamelogs(player_id: int, limit: int) -> str:
    return f"player:gamelogs:{player_id}:{limit}"


def projections_today(lookback: int) -> str:
    return f"projections:today:{lookback}"


def projections_player(player_id: int, game_id: int, lookback: int) -> str:
    return f"projections:player:{player_id}:game:{game_id}:{lookback}"


def injuries_today() -> str:
    return "injuries:today"


# ── Bust patterns (glob) ──────────────────────────────────────────────────────
# Used with cache_delete_pattern() after ingestion writes.

PATTERN_PROJECTIONS_ALL = "projections:*"
PATTERN_PLAYER_STATS_ALL = "player:stats:*"
PATTERN_PLAYER_GAMELOGS_ALL = "player:gamelogs:*"
