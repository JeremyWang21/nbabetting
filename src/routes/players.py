from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.game import Game
from src.models.game_log import PlayerGameLog
from src.models.player import Player
from src.models.team import Team
from src.utils.date_utils import today_et
from src.schemas.player import PlayerSearchResponse
from src.schemas.stats import GameLogResponse, PlayerStatsResponse
from src.services.projection_service import MARKET_TO_FIELD

# Combo markets: computed as sum of multiple columns
COMBO_MARKETS: dict[str, list[str]] = {
    "player_pa":  ["points", "assists"],
    "player_ra":  ["rebounds", "assists"],
    "player_pra": ["points", "rebounds", "assists"],
}
from src.services.stats_service import StatsService

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search", response_model=PlayerSearchResponse)
async def search_players(
    q: str = Query(..., min_length=2, description="Player name search query"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    return await StatsService(db).search_players(q, limit)


@router.get("/by-team/{team_id}", response_model=PlayerSearchResponse)
async def players_by_team(team_id: int, db: AsyncSession = Depends(get_db)):
    return await StatsService(db).get_players_by_team(team_id)


@router.get("/{player_id}/stats", response_model=PlayerStatsResponse)
async def get_player_stats(player_id: int, db: AsyncSession = Depends(get_db)):
    return await StatsService(db).get_player_stats(player_id)


@router.get("/{player_id}/gamelogs", response_model=list[GameLogResponse])
async def get_player_gamelogs(
    player_id: int,
    limit: int = Query(10, ge=1, le=82),
    db: AsyncSession = Depends(get_db),
):
    return await StatsService(db).get_player_gamelogs(player_id, limit)


@router.get("/{player_id}/chart-data")
async def get_player_chart_data(
    player_id: int,
    market: str = Query("player_points"),
    lookback: int = Query(15, ge=3, le=82),
    opponent_team_id: int | None = Query(None),
    min_minutes: float = Query(0, ge=0, le=60),
    game_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return per-game values + dates for charting, plus season average for reference line."""
    combo_fields = COMBO_MARKETS.get(market)
    field = MARKET_TO_FIELD.get(market)
    if field is None and combo_fields is None:
        return {"labels": [], "values": [], "minutes": [], "game_ids": [], "avg": None, "b2b": False}

    # For combos, require all component fields to be non-null
    conditions = [PlayerGameLog.player_id == player_id]
    if combo_fields:
        for f in combo_fields:
            conditions.append(getattr(PlayerGameLog, f).is_not(None))
    else:
        conditions.append(getattr(PlayerGameLog, field).is_not(None))

    if opponent_team_id:
        conditions.append(
            (Game.home_team_id == opponent_team_id) | (Game.away_team_id == opponent_team_id)
        )

    result = await db.execute(
        select(PlayerGameLog, Game.game_date, Game.home_team_id, Game.away_team_id)
        .join(Game, PlayerGameLog.game_id == Game.id)
        .where(*conditions)
        .order_by(Game.game_date.desc())
        .limit(lookback * 3 if min_minutes > 0 else lookback)
    )
    rows = result.all()

    # get player team for opponent label
    player = await db.get(Player, player_id)
    player_team_id = player.team_id if player else None

    team_ids = {r.home_team_id for r in rows} | {r.away_team_id for r in rows}
    if team_ids:
        t_result = await db.execute(select(Team.id, Team.abbreviation).where(Team.id.in_(team_ids)))
        team_abbr = {row.id: row.abbreviation for row in t_result}
    else:
        team_abbr = {}

    def get_value(log) -> float:
        if combo_fields:
            return float(sum(getattr(log, f) or 0 for f in combo_fields))
        return float(getattr(log, field))

    # reverse so oldest → newest for chart
    rows = list(reversed(rows))
    labels, values, minutes_list, game_ids = [], [], [], []
    for row in rows:
        log, gdate, home_tid, away_tid = row[0], row.game_date, row.home_team_id, row.away_team_id
        mins = float(log.minutes) if log.minutes is not None else 0.0
        if min_minutes > 0 and mins < min_minutes:
            continue
        if len(values) >= lookback:
            break
        opp_id = away_tid if player_team_id and home_tid == player_team_id else home_tid
        opp = team_abbr.get(opp_id, "?")
        labels.append(f"{gdate.strftime('%m/%d')} vs {opp}")
        values.append(get_value(log))
        minutes_list.append(mins)
        game_ids.append(log.game_id)

    avg = round(sum(values) / len(values), 1) if values else None

    # B2B: did the player's team play the day before their upcoming game?
    # Must use game_id to get the correct game date — otherwise when showing tomorrow's
    # games, today_et()-1 gives the wrong reference date.
    b2b = False
    if game_id and player:
        tonight = await db.get(Game, game_id)
        if tonight:
            # Determine which team the player is on for this game
            if tonight.home_team_id == player.team_id:
                team_id_for_b2b = player.team_id
            elif tonight.away_team_id == player.team_id:
                team_id_for_b2b = player.team_id
            else:
                # stale team_id — can't determine reliably, skip B2B
                team_id_for_b2b = None

            if team_id_for_b2b:
                day_before = tonight.game_date - timedelta(days=1)
                b2b_result = await db.execute(
                    select(Game.id).where(
                        Game.game_date == day_before,
                        (Game.home_team_id == team_id_for_b2b) | (Game.away_team_id == team_id_for_b2b),
                    ).limit(1)
                )
                b2b = b2b_result.scalar_one_or_none() is not None

    return {"labels": labels, "values": values, "minutes": minutes_list, "game_ids": game_ids, "avg": avg, "field": field, "market": market, "b2b": b2b}
