"""Item 3: mode/project replace must shutdown previous engine."""

from face_swap_studio.engines.lifecycle import replace_engine, shutdown_engine
from face_swap_studio.engines.placeholder import PlaceholderEngine


class TrackingEngine(PlaceholderEngine):
    def __init__(self) -> None:
        super().__init__()
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        super().shutdown()


def test_replace_engine_shuts_down_old():
    old = TrackingEngine()
    created = []

    def factory(name: str):
        eng = TrackingEngine()
        created.append(name)
        return eng

    new = replace_engine(old, "placeholder", factory=factory)
    assert old.shutdown_calls == 1
    assert new is not old
    assert created == ["placeholder"]


def test_shutdown_engine_none_safe():
    shutdown_engine(None)
