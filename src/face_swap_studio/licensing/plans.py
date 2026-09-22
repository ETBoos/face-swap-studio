"""USDT plan catalog — product shell stubs (no chain broadcast yet)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    notes: str = ""


PLAN_CATALOG: dict[PlanTier, PlanSpec] = {
    PlanTier.STARTER: PlanSpec(
        tier=PlanTier.STARTER,
        name_zh="Starter",
        annual_usdt=199,
        seats=1,
        allow_simple=True,
        allow_pro_dfm=False,
        notes="简易模式 · 1 席位 · 基础工程",
    ),
    PlanTier.PRO: PlanSpec(
        tier=PlanTier.PRO,
        name_zh="Pro",
        annual_usdt=599,
        seats=3,
        allow_simple=True,
        allow_pro_dfm=True,
        notes="简易 + 顶级 dfm · 3 席位",
    ),
    PlanTier.STUDIO: PlanSpec(
        tier=PlanTier.STUDIO,
        name_zh="Studio",
        annual_usdt=1499,
        seats=10,
        allow_simple=True,
        allow_pro_dfm=True,
        notes="多机授权 · 优先支持 · 可加白",
    ),
}

EXTRA_SEAT_USDT_PER_YEAR = 79


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


@dataclass
class LicenseState:
    tier: PlanTier = PlanTier.STARTER
    seats: int = 1
    dfm_enabled: bool = False
    usdt_network: str = "TRC20"  # TRC20 | ERC20
    payment_address: str = ""  # display-only until merchant sets
    last_txid: str = ""
    active: bool = False  # True after mocked/on-chain confirm callback
    # Trial codes (FS-1D / FS-30D). Empty when unactivated. USDT does not use these.
    activation_code: str = ""
    activated_at: str = ""  # ISO-8601 UTC
    expires_at: str = ""  # ISO-8601 UTC; trial end, exclusive
    used_codes: list[str] = field(default_factory=list)

    def usdt_paid(self) -> bool:
        """Formal annual unlock. Trial activation does not set this."""
        return bool(self.active and self.last_txid and len(self.last_txid) >= 8)

    def trial_current(self, *, now: datetime | None = None) -> bool:
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False
        current = _as_utc(now or datetime.now(timezone.utc))
        return current < _as_utc(expires)

    def allows_preview(self, *, now: datetime | None = None) -> bool:
        """Preview/start is on for a current trial or a valid USDT license."""
        return self.usdt_paid() or self.trial_current(now=now)

    def allows_pro_dfm(self) -> bool:
        spec = PLAN_CATALOG[self.tier]
        return bool(self.active and spec.allow_pro_dfm and self.dfm_enabled)

    def allows_simple(self, *, now: datetime | None = None) -> bool:
        spec = PLAN_CATALOG[self.tier]
        return bool(spec.allow_simple and self.allows_preview(now=now))
