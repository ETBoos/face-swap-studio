"""Engine replace helper — always shutdown previous before create."""

from __future__ import annotations

from typing import Callable, Optional

from face_swap_studio.engines.base import FaceSwapEngine


def shutdown_engine(engine: Optional[FaceSwapEngine]) -> None:
    if engine is None:
        return
    try:
        engine.shutdown()
    except Exception:
        pass


def replace_engine(
    old: Optional[FaceSwapEngine],
    engine_name: str,
    *,
    factory: Callable[[str], FaceSwapEngine],
) -> FaceSwapEngine:
    """Stop/shutdown ``old`` then return ``factory(engine_name)``."""
    shutdown_engine(old)
    return factory(engine_name)
