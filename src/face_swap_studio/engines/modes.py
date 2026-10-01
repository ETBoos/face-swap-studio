"""Product work modes: simple (FaceFusion) vs pro (DeepFaceLive + .dfm)."""

from __future__ import annotations

from enum import Enum


class WorkMode(str, Enum):
    """User-facing mode switch."""

    SIMPLE = "simple"  # FaceFusion — easy config, no .dfm
    PRO = "pro"  # DeepFaceLive — separately trained .dfm model


MODE_LABELS_ZH = {
    WorkMode.SIMPLE: "照片模式",
    WorkMode.PRO: "专业人物模型（.dfm）",
}

MODE_ENGINE_IDS = {
    WorkMode.SIMPLE: "facefusion",
    WorkMode.PRO: "deepfacelive",
}
