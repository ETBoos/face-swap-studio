"""Product work modes: 即用 (Deep-Live-Cam) vs 专模 (DeepFaceLive + .dfm)."""

from __future__ import annotations

from enum import Enum


class WorkMode(str, Enum):
    """User-facing mode switch."""

    SIMPLE = "simple"  # 即用 — Deep-Live-Cam, import a face image, no .dfm
    PRO = "pro"  # 专模 — DeepFaceLive, load .dfm


MODE_LABELS_ZH = {
    WorkMode.SIMPLE: "即用（Deep-Live-Cam · 导入脸图）",
    WorkMode.PRO: "专模（DeepFaceLive · 加载 .dfm）",
}

MODE_ENGINE_IDS = {
    WorkMode.SIMPLE: "deeplivecam",
    WorkMode.PRO: "deepfacelive",
}
