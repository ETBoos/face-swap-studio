from pathlib import Path

import pytest

from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.licensing.store import LicenseStore


def test_set_tier_and_callback(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    store.set_tier(PlanTier.PRO)
    assert store.state.seats == 3
    assert store.state.dfm_enabled is True
    out = store.apply_usdt_payment_callback(
        txid="abc123456789", network="TRC20", amount_usdt=599
    )
    assert out["ok"] is True
    assert store.state.active is True


def test_starter_blocks_dfm(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    store.set_tier(PlanTier.STARTER)
    with pytest.raises(PermissionError):
        store.set_dfm_enabled(True)
