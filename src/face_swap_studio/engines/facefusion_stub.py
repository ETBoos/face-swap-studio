"""Compatibility imports; photo mode now uses the real isolated adapter."""

from .facefusion import FaceFusionEngine, create_facefusion_engine

FaceFusionStubEngine = FaceFusionEngine

__all__ = ["FaceFusionEngine", "FaceFusionStubEngine", "create_facefusion_engine"]
