from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.game import Game
from src.models.injury import InjuryReport
from src.models.player import Player
from src.models.team import Team
from src.schemas.game import TodaysGamesResponse
from src.services.game_service import GameService

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/today", response_model=TodaysGamesResponse)
async def get_todays_games(db: AsyncSession = Depends(get_db)):
    return await GameService(db).get_todays_games()


@router.get("/{game_id}/players")
async def get_game_players(game_id: int, db: AsyncSession = Depends(get_db)):
    """Return active players for both teams in a game, with injury status."""
    from src.models.game_log import PlayerGameLog
    from fastapi import HTTPException

    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    team_ids = [game.home_team_id, game.away_team_id]

    # load team abbreviations
    t_result = await db.execute(
        select(Team.id, Team.abbreviation).where(Team.id.in_(team_ids))
    )
    team_abbr = {row.id: row.abbreviation for row in t_result}

    # Primary source: players by current team_id
    p_result = await db.execute(
        select(Player).where(
            Player.team_id.in_(team_ids),
            Player.is_active.is_(True),
        )
    )
    players_by_team = {p.id: p for p in p_result.scalars().all()}

    # Fallback: any player who has a game log for this game (catches stale team_id)
    log_result = await db.execute(
        select(PlayerGameLog.player_id).where(PlayerGameLog.game_id == game_id)
    )
    logged_player_ids = [r[0] for r in log_result.all()]
    if logged_player_ids:
        extra_result = await db.execute(
            select(Player).where(Player.id.in_(logged_player_ids))
        )
        for p in extra_result.scalars().all():
            if p.id not in players_by_team:
                players_by_team[p.id] = p

    players = sorted(players_by_team.values(), key=lambda p: p.full_name)

    # For players whose team_id doesn't match either team, assign by game log
    log_team_result = await db.execute(
        select(PlayerGameLog.player_id, Player.team_id)
        .join(Player, PlayerGameLog.player_id == Player.id)
        .where(PlayerGameLog.game_id == game_id)
    )
    # Build a map: player_id → which team they played for in this specific game
    # We infer from their current team_id if it matches, else assign to closest team via log
    player_game_team: dict[int, int] = {}
    for row in log_team_result.all():
        pid, tid = row[0], row[1]
        if tid in team_ids:
            player_game_team[pid] = tid

    # load injury status
    player_ids = [p.id for p in players]
    inj_result = await db.execute(
        select(InjuryReport.player_id, InjuryReport.status, InjuryReport.injury_description)
        .where(InjuryReport.player_id.in_(player_ids), InjuryReport.status == "OUT")
        .order_by(InjuryReport.reported_at.desc())
    )
    out_players = {row.player_id: row.injury_description for row in inj_result}

    result = []
    for p in players:
        # Determine which team this player is on for this game
        if p.team_id in team_ids:
            effective_team_id = p.team_id
        elif p.id in player_game_team:
            effective_team_id = player_game_team[p.id]
        else:
            # Can't place this player on either team — skip them
            continue
        is_out = p.id in out_players
        result.append({
            "id": p.id,
            "full_name": p.full_name,
            "position": p.position,
            "jersey_number": p.jersey_number,
            "team_id": effective_team_id,
            "team_abbr": team_abbr.get(effective_team_id),
            "status": "OUT" if is_out else "ACTIVE",
            "injury_note": out_players.get(p.id),
        })

    home_abbr = team_abbr.get(game.home_team_id)
    away_abbr = team_abbr.get(game.away_team_id)
    return {
        "game_id": game_id,
        "home_team_id": game.home_team_id,
        "away_team_id": game.away_team_id,
        "home_team_abbr": home_abbr,
        "away_team_abbr": away_abbr,
        "players": result,
    }


@router.get("/{game_id}/full-boxscore")
async def get_full_boxscore(game_id: int, db: AsyncSession = Depends(get_db)):
    """Return full box score for both teams in a game."""
    from datetime import timedelta
    from src.models.game_log import PlayerGameLog
    from fastapi import HTTPException

    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    team_ids = [game.home_team_id, game.away_team_id]
    t_result = await db.execute(
        select(Team.id, Team.abbreviation, Team.name).where(Team.id.in_(team_ids))
    )
    teams = {row.id: row for row in t_result}

    # All game logs for this game
    log_result = await db.execute(
        select(PlayerGameLog, Player.full_name, Player.position, Player.team_id)
        .join(Player, PlayerGameLog.player_id == Player.id)
        .where(PlayerGameLog.game_id == game_id)
        .order_by(PlayerGameLog.points.desc().nullslast())
    )
    log_rows = log_result.all()

    # Active roster for teams (for scheduled games with no logs)
    p_result = await db.execute(
        select(Player).where(
            Player.team_id.in_(team_ids),
            Player.is_active.is_(True),
        ).order_by(Player.full_name)
    )
    all_players = p_result.scalars().all()

    # Derive scores from game logs when not stored
    home_score = game.home_score
    away_score = game.away_score
    if (home_score is None or away_score is None) and log_rows:
        score_by_team: dict[int, int] = {}
        for row in log_rows:
            log, _, _, team_id = row[0], row[1], row[2], row[3]
            if log.points is not None:
                score_by_team[team_id] = score_by_team.get(team_id, 0) + log.points
        if game.home_team_id in score_by_team:
            home_score = score_by_team[game.home_team_id]
        if game.away_team_id in score_by_team:
            away_score = score_by_team[game.away_team_id]

    # B2B check
    yesterday = game.game_date - timedelta(days=1)
    b2b_result = await db.execute(
        select(Game.home_team_id, Game.away_team_id).where(Game.game_date == yesterday)
    )
    yesterday_teams: set[int] = set()
    for row in b2b_result:
        yesterday_teams.add(row.home_team_id)
        yesterday_teams.add(row.away_team_id)

    def pct(made, att):
        if made is None or att is None or att == 0:
            return None
        return round(made / att * 100, 1)

    def build_player_row(log, name, pos, team_id, player_id):
        return {
            "player_id": player_id,
            "name": name,
            "position": pos,
            "team_id": team_id,
            "minutes": log.minutes if log else None,
            "points": log.points if log else None,
            "rebounds": log.rebounds if log else None,
            "assists": log.assists if log else None,
            "steals": log.steals if log else None,
            "blocks": log.blocks if log else None,
            "turnovers": log.turnovers if log else None,
            "fg_made": log.fg_made if log else None,
            "fg_attempted": log.fg_attempted if log else None,
            "fg_pct": pct(log.fg_made, log.fg_attempted) if log else None,
            "fg3_made": log.fg3_made if log else None,
            "fg3_attempted": log.fg3_attempted if log else None,
            "fg3_pct": pct(log.fg3_made, log.fg3_attempted) if log else None,
            "ft_made": log.ft_made if log else None,
            "ft_attempted": log.ft_attempted if log else None,
            "ft_pct": pct(log.ft_made, log.ft_attempted) if log else None,
            "plus_minus": log.plus_minus if log else None,
        }

    has_logs = len(log_rows) > 0

    if has_logs:
        home_rows, away_rows = [], []
        for row in log_rows:
            log, name, pos, team_id = row[0], row[1], row[2], row[3]
            entry = build_player_row(log, name, pos, team_id, log.player_id)
            if team_id == game.home_team_id:
                home_rows.append(entry)
            else:
                away_rows.append(entry)
    else:
        # No logs yet — return roster only
        home_rows = [build_player_row(None, p.full_name, p.position, p.team_id, p.id)
                     for p in all_players if p.team_id == game.home_team_id]
        away_rows = [build_player_row(None, p.full_name, p.position, p.team_id, p.id)
                     for p in all_players if p.team_id == game.away_team_id]

    home = teams.get(game.home_team_id)
    away = teams.get(game.away_team_id)

    return {
        "game": {
            "id": game.id,
            "date": game.game_date.strftime("%a %b %-d, %Y"),
            "status": game.status,
            "home_team_id": game.home_team_id,
            "away_team_id": game.away_team_id,
            "home_team_abbr": home.abbreviation if home else None,
            "home_team_name": home.name if home else None,
            "away_team_abbr": away.abbreviation if away else None,
            "away_team_name": away.name if away else None,
            "home_score": home_score,
            "away_score": away_score,
            "home_b2b": game.home_team_id in yesterday_teams,
            "away_b2b": game.away_team_id in yesterday_teams,
        },
        "has_stats": has_logs,
        "home_players": home_rows,
        "away_players": away_rows,
    }


@router.get("/{game_id}/boxscore/{player_id}")
async def get_player_boxscore(game_id: int, player_id: int, db: AsyncSession = Depends(get_db)):
    """Return game summary + full box score line for one player."""
    from datetime import timedelta
    from sqlalchemy import func
    from src.models.game_log import PlayerGameLog
    from fastapi import HTTPException

    game = await db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    # Team info
    team_ids = [game.home_team_id, game.away_team_id]
    t_result = await db.execute(
        select(Team.id, Team.abbreviation, Team.name).where(Team.id.in_(team_ids))
    )
    teams = {row.id: row for row in t_result}

    # Player log for this game
    log_result = await db.execute(
        select(PlayerGameLog).where(
            PlayerGameLog.game_id == game_id,
            PlayerGameLog.player_id == player_id,
        )
    )
    log = log_result.scalar_one_or_none()

    player = await db.get(Player, player_id)

    home = teams.get(game.home_team_id)
    away = teams.get(game.away_team_id)

    # Scores: use stored scores, or derive from game logs if null
    home_score = game.home_score
    away_score = game.away_score
    if home_score is None or away_score is None:
        # Sum points per player grouped by their team via player records
        score_result = await db.execute(
            select(Player.team_id, func.sum(PlayerGameLog.points).label("pts"))
            .join(Player, PlayerGameLog.player_id == Player.id)
            .where(PlayerGameLog.game_id == game_id, PlayerGameLog.points.is_not(None))
            .group_by(Player.team_id)
        )
        score_map = {row.team_id: row.pts for row in score_result}
        home_score = score_map.get(game.home_team_id) or home_score
        away_score = score_map.get(game.away_team_id) or away_score

    # B2B: check if each team played the day before this game
    yesterday = game.game_date - timedelta(days=1)
    b2b_result = await db.execute(
        select(Game.home_team_id, Game.away_team_id)
        .where(Game.game_date == yesterday)
    )
    yesterday_teams: set[int] = set()
    for row in b2b_result:
        yesterday_teams.add(row.home_team_id)
        yesterday_teams.add(row.away_team_id)

    def pct(made, att):
        if made is None or att is None or att == 0:
            return None
        return round(made / att * 100, 1)

    return {
        "game": {
            "id": game.id,
            "date": game.game_date.strftime("%a %b %-d, %Y"),
            "status": game.status,
            "home_team_abbr": home.abbreviation if home else None,
            "home_team_name": home.name if home else None,
            "away_team_abbr": away.abbreviation if away else None,
            "away_team_name": away.name if away else None,
            "home_score": home_score,
            "away_score": away_score,
            "home_b2b": game.home_team_id in yesterday_teams,
            "away_b2b": game.away_team_id in yesterday_teams,
        },
        "player": {
            "id": player_id,
            "name": player.full_name if player else None,
            "team_id": player.team_id if player else None,
        },
        "boxscore": {
            "minutes": log.minutes if log else None,
            "points": log.points if log else None,
            "rebounds": log.rebounds if log else None,
            "assists": log.assists if log else None,
            "steals": log.steals if log else None,
            "blocks": log.blocks if log else None,
            "turnovers": log.turnovers if log else None,
            "fg_made": log.fg_made if log else None,
            "fg_attempted": log.fg_attempted if log else None,
            "fg_pct": pct(log.fg_made, log.fg_attempted) if log else None,
            "fg3_made": log.fg3_made if log else None,
            "fg3_attempted": log.fg3_attempted if log else None,
            "fg3_pct": pct(log.fg3_made, log.fg3_attempted) if log else None,
            "ft_made": log.ft_made if log else None,
            "ft_attempted": log.ft_attempted if log else None,
            "ft_pct": pct(log.ft_made, log.ft_attempted) if log else None,
            "plus_minus": log.plus_minus if log else None,
        } if log else None,
    }
