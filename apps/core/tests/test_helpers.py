from datetime import timedelta

from django.utils.timezone import now

from apps.core.helpers import StandardPagination, elapsed_minutes, format_duration


class TestFormatDuration:
    def test_minutes_only(self):
        assert format_duration(45) == "45m"

    def test_zero_minutes(self):
        assert format_duration(0) == "0m"

    def test_exact_one_hour(self):
        assert format_duration(60) == "1h"

    def test_exact_multiple_hours(self):
        assert format_duration(120) == "2h"

    def test_hours_and_minutes(self):
        assert format_duration(135) == "2h 15m"

    def test_one_minute(self):
        assert format_duration(1) == "1m"

    def test_59_minutes(self):
        assert format_duration(59) == "59m"

    def test_61_minutes(self):
        assert format_duration(61) == "1h 1m"


class TestElapsedMinutes:
    def test_just_now_returns_zero(self):
        assert elapsed_minutes(now()) == 0

    def test_one_hour_ago(self):
        assert elapsed_minutes(now() - timedelta(hours=1)) == 60

    def test_90_minutes_ago(self):
        assert elapsed_minutes(now() - timedelta(minutes=90)) == 90

    def test_partial_minute_is_truncated(self):
        assert elapsed_minutes(now() - timedelta(seconds=90)) == 1

    def test_returns_int(self):
        assert isinstance(elapsed_minutes(now() - timedelta(minutes=5)), int)


class TestStandardPagination:
    def test_default_page_size(self):
        assert StandardPagination.page_size == 25

    def test_max_page_size(self):
        assert StandardPagination.max_page_size == 200

    def test_page_size_query_param(self):
        assert StandardPagination.page_size_query_param == "page_size"
