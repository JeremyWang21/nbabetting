from datetime import date, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.game import Game
from src.models.player import Player
from src.models.prop_snapshot import PropSnapshot
from src.schemas.props import BestLine, BestLinesResponse


class PropsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_best_lines_today(self) -> BestLinesResponse:
        """
        For each (player, game, market) group in today's most recent snapshots,
        find the best over line and best price on each side across all bookmakers.
        """
        today = date.today()

        # Get IDs of today's games
        game_result = await self.db.execute(
            select(Game.id).where(Game.game_date == today)
        )
        game_ids = game_result.scalars().all()
        if not game_ids:
            return BestLinesResponse(props=[], count=0)

        # Fetch the most recent snapshot per (player, game, market, bookmaker)
        # We grab all of today's snapshots and aggregate in Python for simplicity
        snap_result = await self.db.execute(
            select(PropSnapshot)
            .where(PropSnapshot.game_id.in_(game_ids))
            .order_by(PropSnapshot.fetched_at.desc())
        )
        snapshots = snap_result.scalars().all()

        # Group by (player_id, game_id, market_key) — keep newest per bookmaker
        latest: dict[tuple, dict[str, PropSnapshot]] = {}
        for snap in snapshots:
            group_key = (snap.player_id, snap.game_id, snap.market_key)
            book_map = latest.setdefault(group_key, {})
            if snap.bookmaker not in book_map:
                book_map[snap.bookmaker] = snap

        # Fetch player names in one query
        player_ids = {k[0] for k in latest}
        player_map: dict[int, str] = {}
        if player_ids:
            p_result = await self.db.execute(
                select(Player.id, Player.full_name).where(Player.id.in_(player_ids))
            )
            player_map = {row.id: row.full_name for row in p_result}

        best_lines: list[BestLine] = []
        for (player_id, game_id, market_key), book_map in latest.items():
            all_snaps = list(book_map.values())

            # Best over line = highest number (more favorable for over bettors)
            over_snaps = [s for s in all_snaps if s.over_line is not None]
            best_over = max(over_snaps, key=lambda s: s.over_line, default=None)

            # Best over price = highest number (least juice)
            over_price_snaps = [s for s in all_snaps if s.over_price is not None]
            best_over_price = max(over_price_snaps, key=lambda s: s.over_price, default=None)

            # Best under price = highest number (least juice, American odds)
            under_price_snaps = [s for s in all_snaps if s.under_price is not None]
            best_under_price = max(under_price_snaps, key=lambda s: s.under_price, default=None)

            best_lines.append(
                BestLine(
                    player_id=player_id,
                    player_name=player_map.get(player_id, "Unknown"),
                    game_id=game_id,
                    market_key=market_key,
                    best_over_line=best_over.over_line if best_over else None,
                    best_over_book=best_over.bookmaker if best_over else None,
                    best_over_price=best_over_price.over_price if best_over_price else None,
                    best_under_price=best_under_price.under_price if best_under_price else None,
                    best_under_book=best_under_price.bookmaker if best_under_price else None,
                    fetched_at=all_snaps[0].fetched_at if all_snaps else None,
                )
            )

        return BestLinesResponse(props=best_lines, count=len(best_lines))

    async def get_game_props(self, game_id: int) -> BestLinesResponse:
        snap_result = await self.db.execute(
            select(PropSnapshot)
            .where(PropSnapshot.game_id == game_id)
            .order_by(PropSnapshot.fetched_at.desc())
        )
        snapshots = snap_result.scalars().all()

        player_ids = {s.player_id for s in snapshots}
        player_map: dict[int, str] = {}
        if player_ids:
            p_result = await self.db.execute(
                select(Player.id, Player.full_name).where(Player.id.in_(player_ids))
            )
            player_map = {row.id: row.full_name for row in p_result}

        latest: dict[tuple, dict[str, PropSnapshot]] = {}
        for snap in snapshots:
            group_key = (snap.player_id, snap.market_key)
            book_map = latest.setdefault(group_key, {})
            if snap.bookmaker not in book_map:
                book_map[snap.bookmaker] = snap

        best_lines: list[BestLine] = []
        for (player_id, market_key), book_map in latest.items():
            all_snaps = list(book_map.values())
            over_snaps = [s for s in all_snaps if s.over_line is not None]
            best_over = max(over_snaps, key=lambda s: s.over_line, default=None)
            over_price_snaps = [s for s in all_snaps if s.over_price is not None]
            best_over_price = max(over_price_snaps, key=lambda s: s.over_price, default=None)
            under_price_snaps = [s for s in all_snaps if s.under_price is not None]
            best_under_price = max(under_price_snaps, key=lambda s: s.under_price, default=None)

            best_lines.append(
                BestLine(
                    player_id=player_id,
                    player_name=player_map.get(player_id, "Unknown"),
                    game_id=game_id,
                    market_key=market_key,
                    best_over_line=best_over.over_line if best_over else None,
                    best_over_book=best_over.bookmaker if best_over else None,
                    best_over_price=best_over_price.over_price if best_over_price else None,
                    best_under_price=best_under_price.under_price if best_under_price else None,
                    best_under_book=best_under_price.bookmaker if best_under_price else None,
                    fetched_at=all_snaps[0].fetched_at if all_snaps else None,
                )
            )

        return BestLinesResponse(props=best_lines, count=len(best_lines))
