"""Product editions and signed entitlement state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class PlanTier(str, Enum):
    STARTER = "starter"
    PRO = "pro"
    STUDIO = "studio"


@dataclass(frozen=True)
class PlanSpec:
    tier: PlanTier
    name_zh: str
    annual_usdt: int
    seats: int
    allow_simple: bool
    allow_pro_dfm: bool
    features: frozenset[str]
    notes: str = ""


PHOTO_PREVIEW = "photo_preview"
PROFESSIONAL_MODEL = "professional_model"
VIRTUAL_OUTPUT = "virtual_output"
REMOVE_WATERMARK = "remove_watermark"


PLAN_CATALOG: dict[PlanTier, PlanSpec] = {
    PlanTier.STARTER: PlanSpec(
        tier=PlanTier.STARTER,
        name_zh="Starter",
        annual_usdt=199,
        seats=1,
        allow_simple=True,
        allow_pro_dfm=False,
        features=frozenset({PHOTO_PREVIEW, VIRTUAL_OUTPUT}),
        notes="照片换脸 · 1 台设备 · 实时输出",
    ),
    PlanTier.PRO: PlanSpec(
        tier=PlanTier.PRO,
        name_zh="Pro",
        annual_usdt=599,
        seats=3,
        allow_simple=True,
        allow_pro_dfm=True,
        features=frozenset({PHOTO_PREVIEW, PROFESSIONAL_MODEL, VIRTUAL_OUTPUT, REMOVE_WATERMARK}),
        notes="照片换脸 + 专业人物模型 · 3 台设备",
    ),
    PlanTier.STUDIO: PlanSpec(
        tier=PlanTier.STUDIO,
        name_zh="Studio",
        annual_usdt=1499,
        seats=10,
        allow_simple=True,
        allow_pro_dfm=True,
        features=frozenset({PHOTO_PREVIEW, PROFESSIONAL_MODEL, VIRTUAL_OUTPUT, REMOVE_WATERMARK}),
        notes="多机授权 · 专业人物模型 · 优先支持",
    ),
}

EXTRA_SEAT_USDT_PER_YEAR = 79


@dataclass
class LicenseState:
    tier: PlanTier = PlanTier.STARTER
    seats: int = 1
    dfm_enabled: bool = False
    active: bool = False
    license_id: str = ""
    key_hint: str = ""
    expires_at: str = ""
    token_expires_at: str = ""
    last_checked_at: str = ""
    device_id: str = ""
    features: list[str] = field(default_factory=list)
    signed_token: str = ""

    def _before(self, value: str, *, now: datetime | None = None) -> bool:
        if not value:
            return False
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return (now or datetime.now(UTC)) < moment

    def is_valid(self, *, now: datetime | None = None) -> bool:
        return bool(
            self.active
            and self.signed_token
            and self._before(self.expires_at, now=now)
            and self._before(self.token_expires_at, now=now)
        )

    def has_feature(self, feature: str, *, now: datetime | None = None) -> bool:
        return self.is_valid(now=now) and feature in self.features

    def allows_pro_dfm(self) -> bool:
        return self.has_feature(PROFESSIONAL_MODEL) and self.dfm_enabled

    def allows_simple(self) -> bool:
        # The branded shell deliberately allows a watermarked local preview
        # before purchase so customers can verify their hardware and result.
        return True

    def allows_output(self) -> bool:
        return self.has_feature(VIRTUAL_OUTPUT)

    def allows_watermark_removal(self) -> bool:
        return self.has_feature(REMOVE_WATERMARK)
