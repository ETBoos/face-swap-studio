"""USDT plan catalog — product shell stubs (no chain broadcast yet)."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class LicenseState:
    tier: PlanTier = PlanTier.STARTER
    seats: int = 1
    dfm_enabled: bool = False
    usdt_network: str = "TRC20"  # TRC20 | ERC20
    payment_address: str = ""  # display-only until merchant sets
    last_txid: str = ""
    active: bool = False  # True after mocked/on-chain confirm callback

    def allows_pro_dfm(self) -> bool:
        spec = PLAN_CATALOG[self.tier]
        return bool(self.active and spec.allow_pro_dfm and self.dfm_enabled)

    def allows_simple(self) -> bool:
        spec = PLAN_CATALOG[self.tier]
        return bool((not self.active) or spec.allow_simple)
        # inactive → allow local trial of simple for demo; tighten later
