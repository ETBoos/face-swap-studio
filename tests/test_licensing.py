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


def test_usdt_wrong_amount_does_not_upgrade(tmp_path: Path):
    """Item 10: amount check must run BEFORE tier mutation."""
    store = LicenseStore(tmp_path / "license.json")
    assert store.state.tier == PlanTier.STARTER
    assert store.state.active is False
    with pytest.raises(ValueError, match="amount"):
        store.apply_usdt_payment_callback(
            txid="abc123456789",
            network="TRC20",
            amount_usdt=1.0,
            tier=PlanTier.PRO,
        )
    assert store.state.tier == PlanTier.STARTER
    assert store.state.active is False
    assert store.state.dfm_enabled is False


def test_usdt_correct_amount_upgrades(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    out = store.apply_usdt_payment_callback(
        txid="abc123456789",
        network="TRC20",
        amount_usdt=599,
        tier=PlanTier.PRO,
    )
    assert out["ok"] is True
    assert store.state.tier == PlanTier.PRO
    assert store.state.active is True
    assert store.state.dfm_enabled is True


def test_usdt_extra_seats_amount(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    # Pro 599 + 2*79 = 757
    with pytest.raises(ValueError):
        store.apply_usdt_payment_callback(
            txid="abc123456789",
            network="TRC20",
            amount_usdt=599,
            tier=PlanTier.PRO,
            extra_seats=2,
        )
    assert store.state.tier == PlanTier.STARTER
    out = store.apply_usdt_payment_callback(
        txid="abc123456789",
        network="TRC20",
        amount_usdt=757,
        tier=PlanTier.PRO,
        extra_seats=2,
    )
    assert out["ok"] is True
    assert store.state.seats == 5  # 3 base + 2


def test_startup_gate_clears_bogus_active(tmp_path: Path):
    path = tmp_path / "license.json"
    path.write_text(
        '{"tier":"pro","seats":3,"dfm_enabled":true,"active":true,'
        '"last_txid":"","usdt_network":"TRC20","payment_address":""}',
        encoding="utf-8",
    )
    store = LicenseStore(path)
    assert store.state.active is False
    assert store.state.dfm_enabled is False
