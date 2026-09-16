"""Local license JSON + USDT payment callback stub."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from face_swap_studio.licensing.plans import (
    EXTRA_SEAT_USDT_PER_YEAR,
    PLAN_CATALOG,
    LicenseState,
    PlanTier,
)


class LicenseStore:
    def __init__(self, path: Path, *, enforce_gate: bool = True) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()
        if enforce_gate:
            self.enforce_startup_gate()

    def _load(self) -> LicenseState:
        if not self.path.is_file():
            return LicenseState()
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        tier = PlanTier(raw.get("tier", PlanTier.STARTER.value))
        return LicenseState(
            tier=tier,
            seats=int(raw.get("seats", PLAN_CATALOG[tier].seats)),
            dfm_enabled=bool(raw.get("dfm_enabled", PLAN_CATALOG[tier].allow_pro_dfm)),
            usdt_network=str(raw.get("usdt_network", "TRC20")),
            payment_address=str(raw.get("payment_address", "")),
            last_txid=str(raw.get("last_txid", "")),
            active=bool(raw.get("active", False)),
        )

    def save(self) -> None:
        data = asdict(self.state)
        data["tier"] = self.state.tier.value
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_tier(self, tier: PlanTier) -> None:
        spec = PLAN_CATALOG[tier]
        self.state.tier = tier
        self.state.seats = spec.seats
        self.state.dfm_enabled = spec.allow_pro_dfm
        self.save()

    def set_dfm_enabled(self, enabled: bool) -> None:
        if enabled and not PLAN_CATALOG[self.state.tier].allow_pro_dfm:
            raise PermissionError("当前档位不含顶级 dfm，请升级 Pro/Studio")
        if enabled and not self.state.active:
            raise PermissionError("授权未激活，无法启用顶级 dfm")
        self.state.dfm_enabled = enabled
        self.save()

    def expected_amount_usdt(self, tier: PlanTier, *, extra_seats: int = 0) -> float:
        if extra_seats < 0:
            raise ValueError("extra_seats must be >= 0")
        base = float(PLAN_CATALOG[tier].annual_usdt)
        return base + float(extra_seats) * float(EXTRA_SEAT_USDT_PER_YEAR)

    def enforce_startup_gate(self) -> list[str]:
        """Hard-check license consistency at startup; demote unsafe state.

        Returns human-readable issue codes that were repaired.
        """
        issues: list[str] = []
        changed = False

        if self.state.active and (not self.state.last_txid or len(self.state.last_txid) < 8):
            self.state.active = False
            issues.append("active_without_txid")
            changed = True

        if self.state.dfm_enabled and not PLAN_CATALOG[self.state.tier].allow_pro_dfm:
            self.state.dfm_enabled = False
            issues.append("dfm_on_disallowed_tier")
            changed = True

        if self.state.dfm_enabled and not self.state.active:
            self.state.dfm_enabled = False
            issues.append("dfm_without_active")
            changed = True

        # Pro/Studio features require active payment; keep tier for UI pricing but block Pro.
        if self.state.tier != PlanTier.STARTER and not self.state.active:
            if self.state.dfm_enabled:
                self.state.dfm_enabled = False
                issues.append("inactive_paid_tier_dfm_cleared")
                changed = True

        if changed:
            self.save()
        return issues

    def apply_usdt_payment_callback(
        self,
        *,
        txid: str,
        network: str,
        amount_usdt: float,
        tier: Optional[PlanTier] = None,
        extra_seats: int = 0,
    ) -> dict[str, Any]:
        """Chain watcher / webhook stub: mark license active after confirmed payment.

        Validates amount (including optional extra seats) BEFORE mutating state.
        Real TRC20/ERC20 verification is NOT implemented here — only the hook.
        """
        if not txid or len(txid) < 8:
            raise ValueError("invalid txid")
        if network.upper() not in ("TRC20", "ERC20"):
            raise ValueError("network must be TRC20 or ERC20")
        if extra_seats < 0:
            raise ValueError("extra_seats must be >= 0")

        target = tier if tier is not None else self.state.tier
        expected = self.expected_amount_usdt(target, extra_seats=extra_seats)
        if amount_usdt + 1e-6 < expected:
            raise ValueError(f"amount {amount_usdt} < plan {expected} USDT")

        # Atomic mutation after all checks pass
        if tier is not None:
            spec = PLAN_CATALOG[tier]
            self.state.tier = tier
            self.state.seats = spec.seats + int(extra_seats)
            self.state.dfm_enabled = spec.allow_pro_dfm
        elif extra_seats:
            self.state.seats = PLAN_CATALOG[self.state.tier].seats + int(extra_seats)

        self.state.usdt_network = network.upper()
        self.state.last_txid = txid
        self.state.active = True
        self.save()
        return {
            "ok": True,
            "tier": self.state.tier.value,
            "seats": self.state.seats,
            "dfm_enabled": self.state.dfm_enabled,
            "txid": txid,
            "expected_usdt": expected,
            "extra_seat_usdt": EXTRA_SEAT_USDT_PER_YEAR,
        }
