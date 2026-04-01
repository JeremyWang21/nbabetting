# NBA Betting Dashboard — Design Document

## Overview

A props.cash-style personal dashboard that aggregates NBA player stats, computes
statistical projections, and lets you compare them against your bookmaker's lines.
Built to be fast, accurate, and deployable to AWS.

---

## Goals

| Goal | Detail |
|---|---|
| Personal use | Access from anywhere via a deployed API |
| Learning | APIs, Docker, AWS (ECR + ECS Fargate + RDS) |
| Data coverage | Projections, custom line entry, game logs, season stats, injuries, matchup data |
| Speed | Redis cache keeps hot endpoints under 10ms |
| Cost | ~$10/month in API subscriptions + ~$33/month AWS |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Client / Browser                    │
│              (FastAPI /docs Swagger UI for now)          │
└─────────────────────────────┬───────────────────────────┘
                              │  HTTP
┌─────────────────────────────▼───────────────────────────┐
│                    FastAPI Application                    │
│                                                          │
│  Routes → Services → (Redis cache-aside) → PostgreSQL   │
│                                                          │
│  Background Scheduler (APScheduler AsyncIOScheduler)     │
│    runs inside the same process                          │
└────┬──────────────────────────────────────────────┬──────┘
     │ writes                                        │ reads
┌────▼──────┐                              ┌─────────▼──────┐
│ PostgreSQL│                              │   Redis 7       │
│ (RDS)     │                              │ (container /    │
│ permanent │                              │  local only)    │
└───────────┘                              └────────────────┘
     ▲
     │ ingesters poll external APIs
┌────┴─────────────────────────────────────────────────────┐
│  External Data Sources                                   │
│                                                          │
│  nba_api  → game logs, season averages, schedules (free) │
│  Tank01   → injury status, live rosters ($10/mo)         │
│  NBA PDF  → official injury designations (free)          │
└──────────────────────────────────────────────────────────┘
```

---

## Data Sources

| Source | Cost | Refresh | Provides |
|---|---|---|---|
| [nba_api](https://github.com/swar/nba_api) | Free | Nightly 4–5am | Game logs, season averages, schedules, defensive stats, rosters |
| [Tank01 RapidAPI Pro](https://rapidapi.com/tank01/api/tank01-fantasy-stats) | $10/mo | Every 15 min | Injury status (OUT/GTD/Q), live rosters |
| NBA Official Injury PDF | Free | Daily ~5pm ET | Formal pre-game injury designations |

**Total API cost: ~$10/month**

No odds API — bookmaker lines are entered manually. Projections are computed
from the stats already in the database.

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12 | Modern typing, async support |
| Web framework | FastAPI | Async-native, auto `/docs`, Pydantic built-in |
| ORM | SQLAlchemy 2.0 async + asyncpg | Type-safe queries, Alembic migrations |
| Migrations | Alembic | Schema versioning, async support |
| Cache | Redis 7 + redis-py async (local only — not on AWS) | Sub-millisecond TTL cache in dev/local |
| Scheduler | APScheduler **3.10.x** (AsyncIOScheduler) | Periodic polling without Celery overhead — must use 3.x, not 4.x |
| HTTP client | httpx async | Tank01 API calls, retries, timeouts |
| Settings | Pydantic BaseSettings | Typed env vars, `.env` file |
| Container | Docker + Docker Compose | Dev/prod parity |
| Registry | AWS ECR | Docker image storage |
| Compute | AWS ECS Fargate | Serverless containers, no EC2 to manage |
| Database | AWS RDS PostgreSQL 16 | Managed Postgres |

---

## Project Structure

```
nbabetting/
├── Dockerfile
├── docker-compose.yml             # Local dev: app + postgres + redis
├── docker-compose.prod.yml        # Production overrides (points at RDS; Redis runs as a sidecar container)
├── requirements.txt
├── requirements-dev.txt
├── alembic.ini
├── scripts/
│   └── bootstrap.py               # One-time seed: teams → players → stats → matchup data
├── deploy/
│   ├── task-definition.json       # ECS task definition template
│   └── ecs-update.sh              # Helper: force new ECS deployment
├── .github/
│   └── workflows/
│       └── deploy.yml             # CI/CD: build → push ECR → update ECS on push to main
├── alembic/
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_custom_lines.py
│       └── 003_add_team_defensive_stats.py
└── src/
    ├── main.py                    # App factory, lifespan, router registration
    ├── config/
    │   └── settings.py            # All env vars (DATABASE_URL, API keys, etc.)
    ├── db/
    │   ├── base.py                # DeclarativeBase with naming conventions
    │   └── session.py             # Async engine, get_db dependency
    ├── cache/
    │   ├── keys.py                # All key names, TTLs, bust patterns
    │   └── redis_client.py        # cache_get / cache_set / cache_delete helpers
    ├── models/
    │   ├── player.py
    │   ├── team.py
    │   ├── game.py
    │   ├── game_log.py
    │   ├── season_averages.py
    │   ├── team_defensive_stats.py
    │   ├── injury.py
    │   ├── custom_line.py
    │   └── prop_snapshot.py       # Reserved for future odds tracking
    ├── schemas/
    │   ├── player.py
    │   ├── game.py
    │   ├── stats.py
    │   ├── injury.py
    │   └── projection.py          # ProjectionResult, CustomLine*, ComparisonRow
    ├── routes/
    │   ├── games.py
    │   ├── players.py
    │   ├── projections.py
    │   ├── custom_lines.py
    │   ├── injuries.py
    │   └── admin.py               # Cache status/flush, scheduler status/trigger
    ├── services/
    │   ├── game_service.py
    │   ├── stats_service.py
    │   ├── projection_service.py  # EWMA + matchup adjustment
    │   ├── custom_line_service.py # CRUD + compare (projection vs your line)
    │   └── injury_service.py
    ├── ingestion/
    │   ├── scheduler.py
    │   ├── nba_stats_ingester.py  # schedule, game logs, season averages
    │   ├── defensive_stats_ingester.py  # opponent stats per team (matchup data)
    │   ├── roster_ingester.py     # players + teams (nba_api static)
    │   ├── injury_ingester.py     # Tank01 + NBA PDF
    │   └── odds_ingester.py       # Stub — reserved if odds API added later
    └── utils/
        ├── http_client.py         # Shared httpx AsyncClient with retries
        └── rate_limiter.py        # 0.6s token bucket for stats.nba.com
```

---

## Database Schema

```
teams
  id, nba_id (UNIQUE), name, abbreviation, city, conference, division
  created_at, updated_at

players
  id, nba_id (UNIQUE), full_name, first_name, last_name
  team_id (no FK — avoids constraint issues during trades)
  position, jersey_number, is_active
  created_at, updated_at

games
  id, nba_game_id (UNIQUE), game_date (INDEX)
  home_team_id → teams, away_team_id → teams
  status ("scheduled" | "in_progress" | "final")
  home_score, away_score, season, season_type
  created_at, updated_at

player_game_logs
  id, player_id → players (INDEX), game_id → games (INDEX)
  UNIQUE(player_id, game_id)
  minutes, points, rebounds, assists, steals, blocks,
  turnovers, fg_made, fg_attempted, fg3_made, fg3_attempted,
  ft_made, ft_attempted, plus_minus, fetched_at

player_season_averages
  id, player_id → players (INDEX), season
  UNIQUE(player_id, season)
  games_played, mpg, ppg, rpg, apg, spg, bpg, fg_pct, fg3_pct, ft_pct
  updated_at

team_defensive_stats                      ← matchup adjustment source
  id, team_id → teams (INDEX), season
  UNIQUE(team_id, season)
  opp_pts_pg, opp_reb_pg, opp_ast_pg, opp_fg3m_pg
  opp_stl_pg, opp_blk_pg, opp_tov_pg, def_rating
  updated_at

injury_reports
  id, player_id → players (INDEX), game_id → games (INDEX, nullable)
  status ("OUT" | "GTD" | "QUESTIONABLE" | "PROBABLE" | "AVAILABLE")
  injury_description, return_date_estimate, source, reported_at (INDEX)

custom_lines                              ← manually entered bookie lines
  id, player_id → players, game_id → games
  market_key, bookmaker (free text)
  over_line (FLOAT), over_price (INT), under_price (INT)
  notes, created_at, updated_at

prop_snapshots                            ← reserved for future odds API
  id, player_id → players, game_id → games
  market_key, bookmaker, over_line, over_price, under_price, fetched_at
  INDEX(player_id, game_id, market_key, fetched_at)
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/v1/games/today` | Today's schedule with scores/status |
| GET | `/api/v1/players/search?q=` | Search players by name |
| GET | `/api/v1/players/{id}/stats` | Season averages + 5 recent games |
| GET | `/api/v1/players/{id}/gamelogs?limit=10` | Paginated game log with opponent |
| GET | `/api/v1/projections/today` | All matchup-adjusted projections for today |
| GET | `/api/v1/projections/{id}?game_id=` | All markets for one player |
| GET | `/api/v1/projections/{id}/{market}?game_id=` | Single market projection |
| GET | `/api/v1/custom-lines` | Today's manually entered lines |
| POST | `/api/v1/custom-lines` | Enter a line from your bookie |
| GET | `/api/v1/custom-lines/compare` | **Projection vs your line: edge, lean, hit rate** |
| PUT | `/api/v1/custom-lines/{id}` | Adjust a line |
| DELETE | `/api/v1/custom-lines/{id}` | Remove a line |
| GET | `/api/v1/injuries` | Today's full injury report |
| GET | `/api/v1/injuries/{player_id}` | Single player's latest status |
| GET | `/api/v1/admin/cache` | Redis key counts by prefix |
| DELETE | `/api/v1/admin/cache?pattern=` | Flush cache keys (default: all) |
| GET | `/api/v1/admin/scheduler` | Job list + next run times |
| POST | `/api/v1/admin/scheduler/{job_id}/run` | Trigger a job immediately |

---

## Caching Strategy

Cache-aside throughout: check Redis first; on miss, query Postgres, write to Redis, return.

| Redis Key | TTL | Busted by |
|---|---|---|
| `games:today` | 30 min | `ingest_todays_games` |
| `player:stats:{id}` | 6 hours | `ingest_game_logs`, `ingest_season_averages` |
| `player:gamelogs:{id}:{limit}` | 6 hours | `ingest_game_logs` |
| `projections:today:{lookback}` | 30 min | `ingest_game_logs`, `ingest_defensive_stats` |
| `projections:player:{id}:game:{gid}:{lb}` | 30 min | `ingest_game_logs`, `ingest_defensive_stats` |
| `injuries:today` | 15 min | `ingest_injury_report` |

---

## Background Scheduler Jobs

| Job | Trigger | Source |
|---|---|---|
| `ingest_todays_games` | Every 30 min | nba_api live scoreboard |
| `ingest_injury_report` | Every 15 min | Tank01 + NBA PDF |
| `ingest_game_logs` | Daily 4:00am | nba_api LeagueGameLog |
| `ingest_season_averages` | Daily 4:30am | nba_api LeagueDashPlayerStats |
| `ingest_defensive_stats` | Daily 5:00am | nba_api LeagueDashTeamStats (Opponent + Advanced) |
| `ingest_roster_updates` | Daily 6:00am | nba_api static + CommonAllPlayers |

All jobs run inside the FastAPI process via `lifespan`. No Celery, no separate worker.

---

## Projection Algorithm

**Step 1 — EWMA base:**
Exponentially weighted moving average of last N games (default 15, configurable).
Decay = 0.85: most recent game weight = 1.0, previous = 0.85, two back = 0.72, etc.

**Step 2 — Matchup adjustment:**
```
factor = opponent_allowed_per_game / league_avg_allowed_per_game
adjusted = ewma_base × factor
```

| factor | label |
|---|---|
| ≥ 1.10 | very favorable |
| 1.04–1.09 | favorable |
| 0.97–1.03 | neutral |
| 0.91–0.96 | tough |
| < 0.91 | very tough |

Applies to: `player_points`, `player_rebounds`, `player_assists`, `player_threes`.
Not applied to: `player_blocks`, `player_steals`, `player_turnovers` (player-side stats).

**Output per projection:**
`projected_value` (EWMA), `adjusted_projection` (use this), `matchup_factor`,
`matchup_label`, `floor` (25th pct), `ceiling` (75th pct), `std_dev`, `sample_size`

**Compare view adds:**
`your_line`, `edge` = adjusted_projection − your_line, `lean` (over/under/push),
`hit_rate_over`, `hit_rate_under` (% of last N games player exceeded the line)

---

## Data Flow

```
  nba_api          ──▶  nba_stats_ingester     ──▶  games, game_logs, season_avgs
  nba_api          ──▶  defensive_stats_ingester ──▶  team_defensive_stats
  nba_api static   ──▶  roster_ingester         ──▶  players, teams
  Tank01 + PDF     ──▶  injury_ingester         ──▶  injury_reports
                                  │
                           bust Redis keys
                                  │
  GET /projections/today
    → cache miss → DB query → EWMA + matchup → write cache → return
    → cache hit  → deserialize → return (< 5ms)

  POST /custom-lines  →  write DB
  GET  /custom-lines/compare
    → for each line: project_player() (cache hit) → hit_rate() → edge → lean
    → sort by |edge| desc → return
```

---

## AWS Deployment Path

### Phase 1 — Local Docker ✅ (start here)
```bash
cp .env.example .env          # fill in TANK01_API_KEY
docker-compose up --build
docker-compose exec app alembic upgrade head
docker-compose exec app python scripts/bootstrap.py
curl http://localhost:8000/health
# browse http://localhost:8000/docs
```

### Phase 2 — Push image to ECR
```bash
aws ecr create-repository --repository-name nbabetting --region us-east-1

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker build -t nbabetting .
docker tag nbabetting:latest \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/nbabetting:latest
docker push \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/nbabetting:latest
```

### Phase 3 — RDS
```bash
# Create RDS PostgreSQL (db.t3.micro, ~$20/month)
# Redis runs as a sidecar container in the ECS task — no ElastiCache needed.

# Run migrations against RDS (temporarily allow your IP in the security group)
DATABASE_URL=postgresql+asyncpg://user:pass@<rds-endpoint>:5432/nbabetting \
  alembic upgrade head
```

### Phase 4 — ECS Fargate
- Use `deploy/task-definition.json` as the template
- Inject secrets from AWS SSM Parameter Store (never hardcode in task def)
- 0.25 vCPU / 512 MB / 1 task — sufficient for personal use
- No load balancer needed initially; use the Fargate public IP

### Phase 5 — CI/CD (GitHub Actions)
Push to `main` → `.github/workflows/deploy.yml` builds, pushes to ECR, forces new ECS deployment automatically.

### AWS steady-state cost

| Service | Config | Monthly |
|---|---|---|
| ECS Fargate | 0.25 vCPU / 512 MB, 1 task (app + Redis sidecar) | ~$10 |
| RDS PostgreSQL | db.t3.micro, 20 GB | ~$20 |
| ECR | Image storage | ~$1 |
| Data transfer | Personal use | ~$2 |
| **Total** | | **~$33** |

---

## Sprint Plan

| Sprint | Deliverable | Status |
|---|---|---|
| 1 | Skeleton: Docker, Alembic, all models/routes/services | ✅ |
| 2 | nba_api ingestion → `/games/today`, `/players/{id}/gamelogs` | ✅ |
| 3 | EWMA projections + matchup data + manual line entry + `/custom-lines/compare` | ✅ |
| 4 | Redis cache-aside (local only) + APScheduler 3.10.x + admin endpoints | ✅ |
| 5 | Injury ingestion (Tank01) + AWS deployment artifacts (ECR/ECS/CI-CD) | ✅ |

---

## Key Design Decisions

**No external odds API** — lines are entered manually. Projections come from nba_api data already in the DB. No ongoing subscription needed for the core workflow.

**APScheduler 3.10.x (not 4.x)** — must use the `3.x` release line. APScheduler 4 has a completely different API and import paths. The `requirements.txt` pins `apscheduler>=3.10.4`. APScheduler runs inside the FastAPI process via `lifespan`; no message broker needed. The `--workers 1` constraint in production is intentional: `AsyncIOScheduler` doesn't coordinate across multiple uvicorn workers.

**Redis local only (no ElastiCache)** — Redis runs as a sidecar container in the ECS task definition alongside the app container. This avoids the ~$15/month ElastiCache cost. The trade-off is that Redis state is lost on task restarts, which is acceptable since all cache data is reconstructed from Postgres within minutes. ElastiCache would only be worth adding if you scale to multiple tasks.

**Cache-aside, not write-through** — ingesters bust Redis keys after writing to Postgres. Redis is always populated lazily. Simpler to reason about; no risk of stale cache on partial writes.

**No FK on `players.team_id`** — avoids constraint violations during mid-season trades where a player's new team may not exist in the DB yet.

**`prop_snapshots` kept but unused** — schema is in place for a future odds API integration without a migration. Currently empty.

**`custom_lines` is free-text bookmaker** — no enum; you can type anything ("DraftKings", "my bookie", "Caesars"). Flexible for personal use.
