"""Compatibility re-export — Pro adapter lives in deepfacelive.py."""

from face_swap_studio.engines.deepfacelive import (  # noqa: F401
    DeepFaceLiveEngine,
    create_engine,
)

# Old tests may import DeepFaceLiveStubEngine
DeepFaceLiveStubEngine = DeepFaceLiveEngine
