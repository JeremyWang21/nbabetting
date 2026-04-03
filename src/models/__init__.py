# Import all models here so Alembic autogenerate can discover them
from src.models.custom_line import CustomLine
from src.models.game import Game
from src.models.team_defensive_stats import TeamDefensiveStats
from src.models.game_log import PlayerGameLog
from src.models.injury import InjuryReport
from src.models.player import Player
from src.models.season_averages import PlayerSeasonAverages
from src.models.team import Team

__all__ = [
    "Player",
    "Team",
    "Game",
    "PlayerGameLog",
    "PlayerSeasonAverages",
    "InjuryReport",
    "CustomLine",
    "TeamDefensiveStats",
]
