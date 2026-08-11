from datetime import UTC, datetime

DEFAULT_TEST_TIME = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class DeterministicClock:
    def __init__(self, current_time: datetime = DEFAULT_TEST_TIME) -> None:
        self._current_time = current_time

    def now(self) -> datetime:
        return self._current_time

    def set(self, current_time: datetime) -> None:
        self._current_time = current_time
