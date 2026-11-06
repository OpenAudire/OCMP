"""When the scheduler runs (pure, so it is tested without waiting).

The Compose ``scheduler`` service records the day's figures once a day at ``RUN_AT`` in the
installation's time zone (``TIMEZONE``, default Africa/Johannesburg), so a "day" is a local day.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

RUN_AT = time(23, 55)  # local time: close to the end of the day the figures describe


def seconds_until_next_run(now: datetime, timezone: str, run_at: time = RUN_AT) -> float:
    """Seconds from ``now`` to the next ``run_at`` in ``timezone`` (always more than zero)."""
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    target = datetime.combine(local.date(), run_at, tzinfo=zone)
    if target <= local:
        target = datetime.combine(local.date() + timedelta(days=1), run_at, tzinfo=zone)
    # Subtract in UTC so a clock change between the two moments is counted.
    return (target.astimezone(ZoneInfo("UTC")) - local.astimezone(ZoneInfo("UTC"))).total_seconds()
