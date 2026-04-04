# NBA Betting Stats Dashboard — Design Document

## Overview

A personal dashboard that aggregates NBA player stats, computes statistical projections,
and lets you compare them against your bookmaker's lines. Built to learn APIs, Docker,
and AWS deployment. Live at **https://jprops.xyz**.

---

## Goals

| Goal | Detail |
|---|---|
| Personal use | Access from anywhere via deployed server |
| Learning | APIs, Docker, AWS (EC2), GitHub Actions CI/CD |
| Data coverage | Projections, custom line entry, game logs, season stats, injuries, matchup data |
| Speed | Redis cache keeps hot endpoints under 10ms |
| Cost | ~$10/month API + ~$8/month EC2 t3.micro |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Client / Browser                    │
│    Single-page dashboard (src/static/index.html)         │
│    Chart.js bar charts · stat tabs · line entry          │
└─────────────────────────────┬───────────────────────────┘
                              │  HTTPS (nginx + certbot)
┌─────────────────────────────▼───────────────────────────┐
│              EC2 t3.micro (Ubuntu, /app)                  │
│                                                          │
│  [nginx] ──▶ [FastAPI app container]                     │
│                  Routes → Services → Redis → PostgreSQL  │
│                  APScheduler (injury ingest only)        │
│                                                          │
│  [postgres container]   [redis container]                │
└──────────────────────────────────────────────────────────┘
         ▲
         │ SSH tunnel (port-forward 5432)
┌────────┴─────────────────────────────────────────────────┐
│              GitHub Actions (ingestion runners)           │
│                                                          │
│  ingest-games.yml   — every 30 min during game hours     │
│  ingest-nightly.yml — daily 4am ET                       │
│                                                          │
│  stats.nba.com is reachable from GitHub IPs (blocked     │
│  on AWS IP ranges), so all nba_api calls run here.       │
│  Data written back to EC2 postgres via SSH tunnel.       │
└──────────────────────────────────────────────────────────┘
         │ nba_api calls
┌────────▼─────────────────────────────────────────────────┐
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
| [nba_api](https://github.com/swar/nba_api) ≥1.11 | Free | Via GitHub Actions | Game logs, season averages, schedules, defensive stats, rosters |
| [Tank01 RapidAPI Pro](https://rapidapi.com/tank01/api/tank01-fantasy-stats) | $10/mo | Every 15 min (APScheduler) | Injury status (OUT/GTD/Q), live rosters |
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
| Cache | Redis 7 + redis-py async | Sub-millisecond TTL cache; runs as Docker container on EC2 |
| Scheduler | APScheduler **3.10.x** (AsyncIOScheduler) | Injury ingest only — must use 3.x, not 4.x |
| HTTP client | httpx async | Tank01 API calls, retries, timeouts |
| Settings | Pydantic BaseSettings | Typed env vars, `.env` file |
| Container | Docker + Docker Compose | Dev/prod parity |
| Compute | AWS EC2 t3.micro | ~$8/mo; persistent process needed for APScheduler |
| Reverse proxy | nginx + certbot | HTTPS via Let's Encrypt, terminates TLS |
| CI/CD | GitHub Actions | Deploy on push + scheduled data ingestion |

**Why EC2 over ECS/Lambda:** APScheduler runs inside the FastAPI process and needs a
persistent container. Lambda is stateless and can't maintain the scheduler. ECS Fargate
would work but costs more for a single personal-use instance.

**Why GitHub Actions for ingestion:** stats.nba.com blocks AWS IP ranges. GitHub Actions
runners use non-blocked IPs, so all nba_api calls are made from there via SSH tunnel
back to the EC2 postgres.

---

## Project Structure

```
nbabetting/
├── Dockerfile
├── docker-compose.yml             # Local dev: app + postgres + redis
├── docker-compose.prod.yml        # EC2 production: app + postgres + redis (restart: unless-stopped)
├── requirements.txt
├── requirements-dev.txt
├── alembic.ini
├── scripts/
│   └── bootstrap.py               # One-time seed: teams → players → stats → matchup data
├── deploy/
│   ├── task-definition.json       # ECS task definition (legacy, not currently used)
│   └── ecs-update.sh              # ECS helper (legacy)
├── .github/
│   └── workflows/
│       ├── deploy.yml             # Push to main → build image → SSH pull + rebuild on EC2
│       ├── ingest-games.yml       # Every 30 min (6pm–8am UTC): live scores via SSH tunnel
│       └── ingest-nightly.yml     # Daily 8am UTC (4am ET): game logs, averages, rosters
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
    │   └── redis_client.py        # cache_get / cache_set / cache_delete (all fail-silently)
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
    │   ├── scheduler.py           # APScheduler — injury ingest only (in-process)
    │   ├── nba_stats_ingester.py  # schedule, game logs, season averages (run via GitHub Actions)
    │   ├── defensive_stats_ingester.py  # opponent stats per team
    │   ├── roster_ingester.py     # players + teams (nba_api static)
    │   ├── injury_ingester.py     # Tank01 + NBA PDF
    │   └── odds_ingester.py       # Stub — reserved if odds API added later
    └── utils/
        ├── http_client.py         # Shared httpx AsyncClient with retries
        ├── rate_limiter.py        # 0.6s token bucket for stats.nba.com
        └── date_utils.py          # today_et(): DST-aware US Eastern date via ZoneInfo
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
| GET | `/api/v1/games/today` | Today's schedule (auto-advances to tomorrow when all Final) |
| GET | `/api/v1/games/{id}/players` | Active players for both teams, with injury status |
| GET | `/api/v1/games/{id}/props` | Best prop lines for a game |
| GET | `/api/v1/players/search?q=` | Search players by name |
| GET | `/api/v1/players/by-team/{team_id}` | All active players for a team |
| GET | `/api/v1/players/{id}/stats` | Season averages + 5 recent games |
| GET | `/api/v1/players/{id}/gamelogs?limit=10` | Paginated game log with opponent |
| GET | `/api/v1/players/{id}/chart-data?market=&lookback=&opponent_team_id=` | Per-game values + labels for Chart.js |
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
All Redis operations fail silently (try/except) so ingestion scripts work even when Redis
is unavailable (e.g. GitHub Actions runners).

| Redis Key | TTL | Busted by |
|---|---|---|
| `games:today` | 30 min | `ingest_todays_games` + admin cache flush |
| `player:stats:{id}` | 6 hours | `ingest_game_logs`, `ingest_season_averages` |
| `player:gamelogs:{id}:{limit}` | 6 hours | `ingest_game_logs` |
| `projections:today:{lookback}` | 30 min | `ingest_game_logs`, `ingest_defensive_stats` |
| `projections:player:{id}:game:{gid}:{lb}` | 30 min | `ingest_game_logs`, `ingest_defensive_stats` |
| `injuries:today` | 15 min | `ingest_injury_report` |

---

## Ingestion Strategy

stats.nba.com blocks AWS IP ranges. To work around this:

- **nba_api ingestion** runs exclusively from **GitHub Actions** runners (non-blocked IPs)
- Data is written to EC2 postgres via an **SSH tunnel** (port-forward 5432)
- After writing, the workflow flushes the relevant Redis keys on EC2 via the admin API
- **Tank01 / injury ingestion** runs inside the FastAPI process via APScheduler (Tank01 is not IP-restricted)

### GitHub Actions Workflows

| Workflow | Schedule | What it runs |
|---|---|---|
| `ingest-games.yml` | Every 30 min, 6pm–8am UTC | `ingest_todays_games()` — live scores |
| `ingest-nightly.yml` | Daily 8am UTC (4am ET) | `ingest_game_logs` → `ingest_season_averages` → `ingest_defensive_stats` → `ingest_roster_updates` → `ingest_todays_games` |

Both workflows:
1. Spin up a Redis service container (so cache calls don't error)
2. Open SSH tunnel to EC2 postgres on `localhost:5432`
3. Run Python ingestion with `DATABASE_URL` pointing at tunnel
4. Call `DELETE /api/v1/admin/cache` to bust EC2 Redis after writes

### Required GitHub Secrets

| Secret | Value |
|---|---|
| `EC2_SSH_KEY` | Contents of the EC2 `.pem` key |
| `EC2_HOST` | EC2 public IP |
| `DB_PASSWORD` | Postgres password |
| `ADMIN_SECRET` | Header secret for admin endpoints |

---

## Background Scheduler Jobs (in-process, APScheduler)

| Job | Trigger | Source |
|---|---|---|
| `ingest_injury_report` | Every 15 min | Tank01 + NBA PDF |

nba_api jobs (game logs, season averages, defensive stats, roster updates, today's schedule)
are handled by GitHub Actions — not APScheduler — due to IP blocking on EC2.

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
  GitHub Actions runner
    → nba_api call (stats.nba.com)
    → SSH tunnel → EC2 postgres write
    → curl DELETE /admin/cache → EC2 Redis flush

  Tank01 (in-process APScheduler)
    → httpx → Tank01 API
    → postgres write → Redis bust

  GET /projections/today
    → cache miss → DB query → EWMA + matchup → write cache → return
    → cache hit  → deserialize → return (< 5ms)

  POST /custom-lines  →  write DB
  GET  /custom-lines/compare
    → for each line: project_player() (cache hit) → hit_rate() → edge → lean
    → sort by |edge| desc → return
```

---

## Deployment

### Live Setup

- **Domain**: jprops.xyz (HTTPS via Let's Encrypt / certbot)
- **Server**: AWS EC2 t3.micro, Ubuntu, `/app` directory
- **Stack**: `docker-compose.prod.yml` — three containers: `app`, `postgres`, `redis`
- **Reverse proxy**: nginx on host, forwards `jprops.xyz` → `localhost:8000`
- **TLS**: certbot auto-renews Let's Encrypt cert

### Deploying code changes

Push to `main` → `deploy.yml` runs:
```
git pull on EC2 → docker-compose up --build -d app
```

Or manually:
```bash
ssh -i ~/Downloads/<key>.pem ec2-user@<EC2_IP> \
  "sudo git -C /app pull && sudo docker-compose -f /app/docker-compose.prod.yml up --build -d app"
```

### Initial EC2 Setup (one-time)

```bash
# On EC2
sudo yum install -y docker git
sudo systemctl start docker
sudo usermod -aG docker ec2-user

# Install docker-compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose

# Clone and start
sudo git clone https://github.com/JeremyWang21/nbabetting /app
cd /app && cp .env.example .env  # fill in secrets
sudo docker-compose -f docker-compose.prod.yml up --build -d
sudo docker-compose -f docker-compose.prod.yml exec app alembic upgrade head
sudo docker-compose -f docker-compose.prod.yml exec app python scripts/bootstrap.py

# nginx + certbot
sudo yum install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d jprops.xyz
```

### AWS cost

| Service | Config | Monthly |
|---|---|---|
| EC2 t3.micro | 1 instance (app + postgres + redis) | ~$8 |
| **Total** | | **~$8** |

---

## Key Design Decisions

**EC2 over ECS/Lambda** — APScheduler needs a persistent process. Lambda is stateless.
ECS Fargate + RDS would cost ~$33/month vs ~$8 for t3.micro with everything containerized.

**GitHub Actions as ingestion compute** — stats.nba.com blocks AWS IP ranges. GitHub
Actions runners use residential/non-datacenter IPs that stats.nba.com allows. All nba_api
calls run there; data is written back via SSH tunnel to EC2 postgres.

**No external odds API** — lines are entered manually. Projections come from nba_api data
already in the DB. No ongoing subscription needed for the core workflow.

**APScheduler 3.10.x (not 4.x)** — must use the `3.x` release line. APScheduler 4 has a
completely different API. The `requirements.txt` pins `apscheduler>=3.10.4`. Runs inside
the FastAPI process via `lifespan`; `--workers 1` in production is intentional.

**Redis on EC2 as a container** — avoids ElastiCache cost. Redis state lost on restart is
acceptable since all data reconstructs from Postgres within minutes.

**Cache-aside, not write-through** — ingesters bust Redis keys after writing to Postgres.
Redis is always populated lazily. Simpler to reason about; no risk of stale cache on
partial writes.

**No FK on `players.team_id`** — avoids constraint violations during mid-season trades
where a player's new team may not exist in the DB yet.

**`prop_snapshots` kept but unused** — schema is in place for a future odds API
integration without a migration. Currently empty.

**US Eastern time for all dates** — the container runs UTC but NBA game dates are ET.
`src/utils/date_utils.py` provides `today_et()` using `zoneinfo.ZoneInfo("America/New_York")`
for correct DST handling. All ingesters and services use this instead of `date.today()`.

**Tomorrow's slate auto-advance** — `game_service.py` checks if all of today's games are
Final; if so, fetches and returns tomorrow's upcoming slate. `ingest_todays_games`
pre-seeds tomorrow's schedule via `_ingest_date_schedule()` when today finishes.

**Historical data seeded manually** — The 2025-26 NBA season started October 22, 2025.
Full season game schedule and box scores were seeded from Mac (non-blocked IP) via direct
postgres connection. ~665 games and ~14,000 player game logs loaded.
