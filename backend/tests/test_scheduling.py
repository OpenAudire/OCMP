"""When the scheduler runs, and which day a figure belongs to (Slice 1.31)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import dashboard_metrics, scheduling


def test_next_run_is_tonight_at_2355_johannesburg_time() -> None:
    # 10:00 UTC is 12:00 in Johannesburg (UTC+2, no daylight saving).
    now = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)
    wait = scheduling.seconds_until_next_run(now, "Africa/Johannesburg")
    assert wait == (11 * 3600) + (55 * 60)


def test_after_the_run_time_it_waits_for_tomorrow() -> None:
    # 21:56 UTC is 23:56 in Johannesburg: just missed, so almost 24 hours.
    now = datetime(2026, 11, 6, 21, 56, tzinfo=UTC)
    wait = scheduling.seconds_until_next_run(now, "Africa/Johannesburg")
    assert wait == 24 * 3600 - 60


def test_exactly_at_the_run_time_waits_a_full_day() -> None:
    now = datetime(2026, 11, 6, 21, 55, tzinfo=UTC)
    assert scheduling.seconds_until_next_run(now, "Africa/Johannesburg") == 24 * 3600


def test_a_clock_change_is_counted() -> None:
    # Europe/London ends daylight saving on 2026-10-25 (01:00 UTC): that day has 25 hours.
    now = datetime(2026, 10, 24, 22, 55, tzinfo=UTC)  # 23:55 BST on the 24th
    wait = scheduling.seconds_until_next_run(now, "Europe/London")
    assert wait == 25 * 3600


def test_the_day_is_the_local_day() -> None:
    # Whatever the server's clock, "today" is read in the named zone.
    auckland = dashboard_metrics.today("Pacific/Auckland")
    samoa = dashboard_metrics.today("Pacific/Pago_Pago")
    assert (auckland - samoa).days in (0, 1)
    assert (
        dashboard_metrics.today("Africa/Johannesburg")
        == datetime.now(ZoneInfo("Africa/Johannesburg")).date()
    )


def test_default_time_zone_is_south_african() -> None:
    settings = Settings(secret_key="x" * 32, database_url="postgresql+asyncpg://u:p@localhost/db")  # type: ignore[arg-type]
    assert settings.timezone == "Africa/Johannesburg"


def test_an_unknown_time_zone_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(
            secret_key="x" * 32,
            database_url="postgresql+asyncpg://u:p@localhost/db",
            timezone="Mars/Olympus",
        )  # type: ignore[arg-type]
