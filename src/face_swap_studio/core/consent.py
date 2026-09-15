"""Consent / authorization checklist for film-crew compliance."""

from __future__ import annotations

CONSENT_CHECKLIST_ZH: list[str] = [
    "已获得出镜演员/脸部素材权利人的书面授权或合同约定",
    "素材仅用于本剧组当前项目的预览/制作，不外传、不用于无关商业用途",
    "已确认不涉及未成年人未经监护人授权的面部素材",
    "预览输出将按需添加水印，并保留使用记录以便审计",
    "理解本工具为预览工作站，正式成片需另行合规审片流程",
]

BANNER_ZH = "仅限授权影视用途 · AUTHORIZED FILM USE ONLY"


def checklist_text() -> str:
    lines = ["授权确认清单（请逐项确认）：", ""]
    for i, item in enumerate(CONSENT_CHECKLIST_ZH, 1):
        lines.append(f"  □ {i}. {item}")
    return "\n".join(lines)
