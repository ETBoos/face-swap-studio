"""Engine adapters — integrate mature live pipelines later."""

from face_swap_studio.engines.base import EngineCapabilities, EngineFrame, FaceSwapEngine
from face_swap_studio.engines.deepfacelive_stub import DeepFaceLiveStubEngine
from face_swap_studio.engines.placeholder import PlaceholderEngine

__all__ = [
    "EngineCapabilities",
    "EngineFrame",
    "FaceSwapEngine",
    "DeepFaceLiveStubEngine",
    "PlaceholderEngine",
]
