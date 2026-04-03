from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.models.game import Game
from src.models.injury import InjuryReport
from src.models.player import Player
from src.models.team import Team
from src.schemas.game import TodaysGamesResponse
from src.schemas.props import BestLinesResponse
from src.services.game_service import GameService
from src.services.props_service import PropsService

router = APIRouter(prefix="/games", tags=["games"])


@router.get("/today", response_model=TodaysGamesResponse)
async def get_todays_games(db: AsyncSession = Depends(get_db)):
    return await GameService(db).get_todays_games()


@router.get("/{game_id}/players")
async def get_game_players(game_id: int, db: AsyncSession = Depends(get_db)):
    """Return active players for both teams in a game, with injury status."""
    game = await db.get(Game, game_id)
    if game is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Game not found")

    team_ids = [game.home_team_id, game.away_team_id]

    # load players for both teams
    p_result = await db.execute(
        select(Player).where(
            Player.team_id.in_(team_ids),
            Player.is_active.is_(True),
        ).order_by(Player.full_name)
    )
    players = p_result.scalars().all()

    # load team abbreviations
    t_result = await db.execute(
        select(Team.id, Team.abbreviation).where(Team.id.in_(team_ids))
    )
    team_abbr = {row.id: row.abbreviation for row in t_result}

    # load latest injury status per player (OUT only — exclude from "playing")
    player_ids = [p.id for p in players]
    inj_result = await db.execute(
        select(InjuryReport.player_id, InjuryReport.status, InjuryReport.injury_description)
        .where(InjuryReport.player_id.in_(player_ids), InjuryReport.status == "OUT")
        .order_by(InjuryReport.reported_at.desc())
    )
    out_players = {row.player_id: row.injury_description for row in inj_result}

    result = []
    for p in players:
        is_out = p.id in out_players
        result.append({
            "id": p.id,
            "full_name": p.full_name,
            "position": p.position,
            "jersey_number": p.jersey_number,
            "team_id": p.team_id,
            "team_abbr": team_abbr.get(p.team_id),
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


@router.get("/{game_id}/props", response_model=BestLinesResponse)
async def get_game_props(game_id: int, db: AsyncSession = Depends(get_db)):
    return await PropsService(db).get_game_props(game_id)
