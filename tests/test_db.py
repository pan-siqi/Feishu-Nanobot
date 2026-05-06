from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nanobot.agent.hiarch_memory.database.ec_database import compute_retention


def test_compute_retention_monotonic():
    r0 = compute_retention(strength=1.0, delta_days=0.0)
    r1 = compute_retention(strength=1.0, delta_days=1.0)
    r7 = compute_retention(strength=1.0, delta_days=7.0)
    assert r0 > r1 > r7


def test_compute_retention_strength_effect():
    # same elapsed days, stronger memory should retain more
    weak = compute_retention(strength=0.5, delta_days=3.0)
    strong = compute_retention(strength=2.0, delta_days=3.0)
    assert strong > weak


def test_review_window_example():
    # Phase 2 rule example: R < 0.4 can be review-candidate
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)
    delta_days = (now - three_days_ago).total_seconds() / 86400.0
    r = compute_retention(strength=1.0, delta_days=delta_days)
    assert r < 0.4