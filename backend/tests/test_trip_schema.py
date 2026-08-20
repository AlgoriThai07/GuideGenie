"""Trip preference schema tests."""

from datetime import time

import pytest
from pydantic import ValidationError

from app.schemas.trip import TripPreferenceCreate


def test_activity_window_defaults_preserve_existing_schedule():
    preference = TripPreferenceCreate()

    assert preference.activity_start_time == time(9, 0)
    assert preference.activity_end_time == time(20, 30)


@pytest.mark.parametrize(
    ("start", "end"),
    [("09:00", "09:00"), ("18:00", "08:00")],
)
def test_activity_window_requires_end_after_start(start, end):
    with pytest.raises(ValidationError, match="activity_end_time must be later"):
        TripPreferenceCreate(
            activity_start_time=start,
            activity_end_time=end,
        )
