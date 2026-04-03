from datetime import date
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def today_et() -> date:
    """Return the current date in US Eastern time (DST-aware)."""
    from datetime import datetime
    return datetime.now(_ET).date()
