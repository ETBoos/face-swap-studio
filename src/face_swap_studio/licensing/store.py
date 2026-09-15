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
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

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
        self.state.dfm_enabled = enabled
        self.save()

    def apply_usdt_payment_callback(
        self,
        *,
        txid: str,
        network: str,
        amount_usdt: float,
        tier: Optional[PlanTier] = None,
    ) -> dict[str, Any]:
        """Chain watcher / webhook stub: mark license active after 'confirmed' payment.

        Real TRC20/ERC20 verification is NOT implemented here — only the hook.
        """
        if not txid or len(txid) < 8:
            raise ValueError("invalid txid")
        if network.upper() not in ("TRC20", "ERC20"):
            raise ValueError("network must be TRC20 or ERC20")
        if tier is not None:
            self.set_tier(tier)
        expected = PLAN_CATALOG[self.state.tier].annual_usdt
        # Soft check: allow exact tier price (extra seats later)
        if amount_usdt + 1e-6 < expected:
            raise ValueError(f"amount {amount_usdt} < plan {expected} USDT")
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
            "extra_seat_usdt": EXTRA_SEAT_USDT_PER_YEAR,
        }
