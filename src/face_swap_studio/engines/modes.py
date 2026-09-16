"""Product work modes: simple (FaceFusion) vs pro (DeepFaceLive + .dfm)."""

from __future__ import annotations

from enum import Enum


class WorkMode(str, Enum):
    """User-facing mode switch."""

    SIMPLE = "simple"  # FaceFusion — easy config, no .dfm
    PRO = "pro"  # DeepFaceLive — separately trained .dfm model


MODE_LABELS_ZH = {
    WorkMode.SIMPLE: "照片模式（FaceFusion）",
    WorkMode.PRO: "专属模型（DeepFaceLive · .dfm）",
}

MODE_ENGINE_IDS = {
    WorkMode.SIMPLE: "facefusion",
    WorkMode.PRO: "deepfacelive",
}
