from datetime import datetime, timedelta, timezone
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


CODE_1D = "FS-1D-MWYT-CDUW-ESHY"
CODE_30D = "FS-30D-E4F2-8A7Z-ARSJ"
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_activate_1d_and_30d(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    one = store.activate_code(f"  {CODE_1D.lower()}  ", now=_T0)
    assert one["ok"] is True
    assert one["duration_days"] == 1
    assert store.state.activation_code == CODE_1D
    assert store.state.tier == PlanTier.STARTER
    assert store.state.active is False
    assert store.state.dfm_enabled is False
    assert store.state.allows_pro_dfm() is False
    activated = datetime.fromisoformat(store.state.activated_at)
    expires = datetime.fromisoformat(store.state.expires_at)
    assert expires - activated == timedelta(days=1)
    assert store.allows_preview(now=_T0) is True
    assert store.allows_preview(now=_T0 + timedelta(hours=23)) is True
    assert CODE_1D in store.state.used_codes

    store30 = LicenseStore(tmp_path / "license30.json")
    thirty = store30.activate_code(CODE_30D, now=_T0)
    assert thirty["duration_days"] == 30
    assert store30.state.tier == PlanTier.STARTER
    assert store30.state.active is False
    activated = datetime.fromisoformat(store30.state.activated_at)
    expires = datetime.fromisoformat(store30.state.expires_at)
    assert expires - activated == timedelta(days=30)
    assert store30.allows_preview(now=_T0 + timedelta(days=29)) is True
    assert store30.state.allows_pro_dfm() is False


def test_reuse_rejected(tmp_path: Path):
    path = tmp_path / "license.json"
    store = LicenseStore(path)
    store.activate_code(CODE_1D, now=_T0)
    with pytest.raises(ValueError, match="已使用"):
        store.activate_code(CODE_1D, now=_T0)
    assert store.state.used_codes.count(CODE_1D) == 1
    assert datetime.fromisoformat(store.state.expires_at) - _T0 == timedelta(days=1)

    reloaded = LicenseStore(path, enforce_gate=False)
    with pytest.raises(ValueError, match="已使用"):
        reloaded.activate_code(CODE_1D, now=_T0 + timedelta(days=3))


def test_expired_trial_blocks_preview_and_does_not_upgrade(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    store.activate_code(CODE_1D, now=_T0)
    assert store.allows_preview(now=_T0 + timedelta(days=1) - timedelta(seconds=1)) is True
    assert store.allows_preview(now=_T0 + timedelta(days=1)) is False

    issues = store.enforce_startup_gate(now=_T0 + timedelta(days=2))
    assert "trial_expired" in issues
    assert store.state.activation_code == ""
    assert store.state.activated_at == ""
    assert store.state.expires_at == ""
    assert CODE_1D in store.state.used_codes
    assert store.state.tier == PlanTier.STARTER
    assert store.state.active is False
    assert store.allows_preview(now=_T0 + timedelta(days=2)) is False
    with pytest.raises(ValueError, match="已使用"):
        store.activate_code(CODE_1D, now=_T0 + timedelta(days=2))


def test_invalid_code_rejected(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    before = store.path.read_text(encoding="utf-8") if store.path.is_file() else ""
    with pytest.raises(ValueError, match="无效"):
        store.activate_code("FS-1D-AAAA-BBBB-CCCC")
    assert store.state.used_codes == []
    assert store.state.activated_at == ""
    assert store.state.expires_at == ""
    assert store.allows_preview() is False
    after = store.path.read_text(encoding="utf-8") if store.path.is_file() else ""
    assert after == before


def test_trial_expiry_keeps_usdt(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json")
    store.activate_code(CODE_30D, now=_T0)
    store.apply_usdt_payment_callback(
        txid="abc123456789",
        network="TRC20",
        amount_usdt=599,
        tier=PlanTier.PRO,
    )
    issues = store.enforce_startup_gate(now=_T0 + timedelta(days=31))
    assert "trial_expired" in issues
    assert store.state.active is True
    assert store.state.tier == PlanTier.PRO
    assert store.state.dfm_enabled is True
    assert store.allows_preview(now=_T0 + timedelta(days=31)) is True
    assert store.state.allows_pro_dfm() is True


def test_seed_code_table_counts():
    from face_swap_studio.licensing.codes import CODE_TABLE

    one = [code for code, days in CODE_TABLE.items() if days == 1]
    thirty = [code for code, days in CODE_TABLE.items() if days == 30]
    assert len(CODE_TABLE) == 40
    assert len(one) == 20
    assert len(thirty) == 20
    assert all(code.startswith("FS-1D-") for code in one)
    assert all(code.startswith("FS-30D-") for code in thirty)


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
