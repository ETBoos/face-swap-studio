"""Product work modes: simple (FaceFusion) vs pro (DeepFaceLive + .dfm)."""

from __future__ import annotations

from enum import Enum


class WorkMode(str, Enum):
    """User-facing mode switch."""

    SIMPLE = "simple"  # FaceFusion — easy config, no .dfm
    PRO = "pro"  # DeepFaceLive — load .dfm for top realism


MODE_LABELS_ZH = {
    WorkMode.SIMPLE: "简易模式（FaceFusion · 无需 dfm）",
    WorkMode.PRO: "顶级模式（DeepFaceLive · 加载 .dfm）",
}

MODE_ENGINE_IDS = {
    WorkMode.SIMPLE: "facefusion",
    WorkMode.PRO: "deepfacelive",
}
