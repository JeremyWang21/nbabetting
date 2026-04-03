from datetime import date, datetime

from pydantic import BaseModel, computed_field


# ── Projection ────────────────────────────────────────────────────────────────

class ProjectionResult(BaseModel):
    """Statistical projection for one player + one market, matchup-adjusted."""
    player_id: int
    player_name: str
    game_id: int
    game_date: date
    opponent: str | None
    market_key: str

    # ── Base projection (EWMA of last N games) ────────────────────────────────
    projected_value: float      # EWMA, before matchup adjustment
    avg_last_n: float           # simple mean, for reference
    sample_size: int            # games used

    # ── Matchup adjustment ────────────────────────────────────────────────────
    # opponent_allowed / league_avg_allowed for this market
    # 1.0 = neutral, >1 = opponent gives up more than avg (favorable), <1 = tough
    matchup_factor: float = 1.0
    # "very favorable" | "favorable" | "neutral" | "tough" | "very tough" | None
    matchup_label: str | None = None
    # projected_value * matchup_factor — this is the number to use
    adjusted_projection: float

    # ── Range / variance ──────────────────────────────────────────────────────
    floor: float        # 25th percentile of sample
    ceiling: float      # 75th percentile of sample
    std_dev: float      # population std dev of sample
    variance: float     # std_dev² — how spread out results are; high = volatile player


# ── Custom line ───────────────────────────────────────────────────────────────

class CustomLineCreate(BaseModel):
    player_id: int
    game_id: int
    market_key: str
    over_line: float
    notes: str | None = None


class CustomLineUpdate(BaseModel):
    over_line: float | None = None
    notes: str | None = None


class CustomLineResponse(BaseModel):
    id: int
    player_id: int
    player_name: str | None = None
    game_id: int
    market_key: str
    over_line: float
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Comparison ────────────────────────────────────────────────────────────────

class ComparisonRow(BaseModel):
    """One row in the comparison table: projection vs your line."""
    player_id: int
    player_name: str
    game_id: int
    game_date: date
    opponent: str | None
    market_key: str
    custom_line_id: int

    your_line: float

    # Statistical projection
    projected_value: float          # EWMA base (before matchup)
    adjusted_projection: float      # after matchup adjustment — use this
    matchup_factor: float
    matchup_label: str | None
    sample_size: int
    floor: float
    ceiling: float
    std_dev: float
    variance: float

    # Hit rate: % of last N games player exceeded your_line
    hit_rate_over: float      # 0.0–1.0
    hit_rate_under: float     # 0.0–1.0
    games_checked: int

    # Edge uses the matchup-adjusted projection (the number to actually act on)
    @computed_field
    @property
    def edge(self) -> float:
        return round(self.adjusted_projection - self.your_line, 2)

    @computed_field
    @property
    def lean(self) -> str:
        return "over" if self.edge > 0 else "under"

    notes: str | None


class ComparisonResponse(BaseModel):
    comparisons: list[ComparisonRow]
    count: int
