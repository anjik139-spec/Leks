"""Daily streak calculations."""

from __future__ import annotations

from datetime import date, timedelta

from bot.services.daily import calculate_streak


def test_streak_counts_today_and_previous_days() -> None:
    today = date(2026, 11, 12)
    days = [
        today.isoformat(),
        (today - timedelta(days=1)).isoformat(),
        (today - timedelta(days=2)).isoformat(),
    ]
    assert calculate_streak(days, today) == 3


def test_streak_shows_yesterday_before_today_checkin() -> None:
    today = date(2026, 11, 12)
    days = [(today - timedelta(days=1)).isoformat()]
    assert calculate_streak(days, today) == 1


def test_streak_resets_after_gap() -> None:
    today = date(2026, 11, 12)
    days = [
        today.isoformat(),
        (today - timedelta(days=2)).isoformat(),
    ]
    assert calculate_streak(days, today) == 1


def test_streak_empty_is_zero() -> None:
    assert calculate_streak([], date(2026, 11, 12)) == 0
