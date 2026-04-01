from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.custom_line import CustomLine
from src.models.game import Game
from src.models.player import Player
from src.schemas.projection import (
    ComparisonResponse,
    ComparisonRow,
    CustomLineCreate,
    CustomLineResponse,
    CustomLineUpdate,
)
from src.services.projection_service import DEFAULT_LOOKBACK, ProjectionService


class CustomLineService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._proj = ProjectionService(db)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create(self, payload: CustomLineCreate) -> CustomLineResponse:
        line = CustomLine(**payload.model_dump())
        self.db.add(line)
        await self.db.commit()
        await self.db.refresh(line)
        return await self._enrich(line)

    async def update(self, line_id: int, payload: CustomLineUpdate) -> CustomLineResponse:
        line = await self.db.get(CustomLine, line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="Custom line not found")

        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(line, field, value)

        await self.db.commit()
        await self.db.refresh(line)
        return await self._enrich(line)

    async def delete(self, line_id: int) -> None:
        line = await self.db.get(CustomLine, line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="Custom line not found")
        await self.db.delete(line)
        await self.db.commit()

    async def get_today(self) -> list[CustomLineResponse]:
        today = date.today()
        result = await self.db.execute(
            select(CustomLine)
            .join(Game, CustomLine.game_id == Game.id)
            .where(Game.game_date == today)
            .order_by(CustomLine.player_id, CustomLine.market_key)
        )
        lines = result.scalars().all()
        return [await self._enrich(line) for line in lines]

    async def get_one(self, line_id: int) -> CustomLineResponse:
        line = await self.db.get(CustomLine, line_id)
        if line is None:
            raise HTTPException(status_code=404, detail="Custom line not found")
        return await self._enrich(line)

    # ── Comparison ────────────────────────────────────────────────────────────

    async def compare_today(
        self, lookback: int = DEFAULT_LOOKBACK
    ) -> ComparisonResponse:
        """
        For every custom line entered today, compute the projection and
        show edge, hit rate, lean.
        """
        today_lines = await self.get_today()

        # Bulk-load player names
        player_ids = {line.player_id for line in today_lines}
        player_map: dict[int, str] = {}
        if player_ids:
            p_result = await self.db.execute(
                select(Player.id, Player.full_name).where(Player.id.in_(player_ids))
            )
            player_map = {row.id: row.full_name for row in p_result}

        rows: list[ComparisonRow] = []
        for line in today_lines:
            proj = await self._proj.project_player(
                line.player_id, line.game_id, line.market_key, lookback
            )
            if proj is None:
                # Not enough game log data yet — skip
                continue

            recent_vals = await self._proj.get_recent_values_for_market(
                line.player_id, line.market_key, lookback
            )
            hit_over, hit_under = self._proj.hit_rate(recent_vals, line.over_line)

            rows.append(
                ComparisonRow(
                    player_id=line.player_id,
                    player_name=player_map.get(line.player_id, "Unknown"),
                    game_id=line.game_id,
                    game_date=proj.game_date,
                    opponent=proj.opponent,
                    market_key=line.market_key,
                    bookmaker=line.bookmaker,
                    custom_line_id=line.id,
                    your_line=line.over_line,
                    your_over_price=line.over_price,
                    your_under_price=line.under_price,
                    projected_value=proj.projected_value,
                    adjusted_projection=proj.adjusted_projection,
                    matchup_factor=proj.matchup_factor,
                    matchup_label=proj.matchup_label,
                    sample_size=proj.sample_size,
                    floor=proj.floor,
                    ceiling=proj.ceiling,
                    std_dev=proj.std_dev,
                    variance=proj.variance,
                    hit_rate_over=hit_over,
                    hit_rate_under=hit_under,
                    games_checked=len(recent_vals),
                    notes=line.notes,
                )
            )

        # Sort by absolute edge descending — biggest edges first
        rows.sort(key=lambda r: abs(r.edge), reverse=True)
        return ComparisonResponse(comparisons=rows, count=len(rows))

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _enrich(self, line: CustomLine) -> CustomLineResponse:
        player = await self.db.get(Player, line.player_id)
        return CustomLineResponse(
            id=line.id,
            player_id=line.player_id,
            player_name=player.full_name if player else None,
            game_id=line.game_id,
            market_key=line.market_key,
            bookmaker=line.bookmaker,
            over_line=line.over_line,
            over_price=line.over_price,
            under_price=line.under_price,
            notes=line.notes,
            created_at=line.created_at,
            updated_at=line.updated_at,
        )
