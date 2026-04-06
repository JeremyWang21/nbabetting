from datetime import date, timedelta, timezone, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.keys import TTL_INJURIES, injuries_today
from src.cache.redis_client import cache_get, cache_set
from src.models.injury import InjuryReport
from src.models.player import Player
from src.schemas.injury import InjuryListResponse, InjuryReportResponse


class InjuryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_todays_injuries(self) -> InjuryListResponse:
        cache_key = injuries_today()

        cached = await cache_get(cache_key)
        if cached is not None:
            return InjuryListResponse.model_validate(cached)

        # Most recent status per player reported in the last 24 hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.db.execute(
            select(InjuryReport)
            .where(InjuryReport.reported_at >= cutoff)
            .order_by(InjuryReport.reported_at.desc())
        )
        all_reports = result.scalars().all()

        # Deduplicate: keep only the most recent report per player
        seen: set[int] = set()
        injuries: list[InjuryReport] = []
        for report in all_reports:
            if report.player_id not in seen:
                seen.add(report.player_id)
                injuries.append(report)

        player_ids = {r.player_id for r in injuries}
        player_map: dict[int, str] = {}
        if player_ids:
            p_result = await self.db.execute(
                select(Player.id, Player.full_name).where(Player.id.in_(player_ids))
            )
            player_map = {row.id: row.full_name for row in p_result}

        responses = [
            InjuryReportResponse(
                id=r.id,
                player_id=r.player_id,
                player_name=player_map.get(r.player_id),
                game_id=r.game_id,
                status=r.status,
                injury_description=r.injury_description,
                return_date_estimate=r.return_date_estimate,
                source=r.source,
                reported_at=r.reported_at,
            )
            for r in injuries
            if r.status != "AVAILABLE"  # only show players with actual restrictions
        ]

        response = InjuryListResponse(injuries=responses, count=len(responses))
        await cache_set(cache_key, response.model_dump(), ttl=TTL_INJURIES)
        return response

    async def get_player_injury_status(
        self, player_id: int
    ) -> InjuryReportResponse | None:
        result = await self.db.execute(
            select(InjuryReport)
            .where(InjuryReport.player_id == player_id)
            .order_by(InjuryReport.reported_at.desc())
            .limit(1)
        )
        injury = result.scalar_one_or_none()
        if injury is None:
            return None

        player = await self.db.get(Player, player_id)
        return InjuryReportResponse(
            id=injury.id,
            player_id=injury.player_id,
            player_name=player.full_name if player else None,
            game_id=injury.game_id,
            status=injury.status,
            injury_description=injury.injury_description,
            return_date_estimate=injury.return_date_estimate,
            source=injury.source,
            reported_at=injury.reported_at,
        )
