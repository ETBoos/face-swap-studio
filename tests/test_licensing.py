"""Signed license, device-seat and local storage checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.licensing.service import LicenseService
from face_swap_studio.licensing.store import LicenseStore
from face_swap_studio.licensing.token import (
    PRODUCT_ID,
    LicenseTokenError,
    public_key_text,
    sign_token,
)

DEVICE_A = "fss-" + "a" * 64
DEVICE_B = "fss-" + "b" * 64


@pytest.fixture
def issuer(tmp_path: Path):
    now = [datetime.now(UTC)]
    key = Ed25519PrivateKey.generate()
    service = LicenseService(tmp_path / "licenses.db", key, clock=lambda: now[0])
    return service, key, now


def create_and_activate(issuer, plan=PlanTier.PRO, device=DEVICE_A):
    service, _, now = issuer
    license_id, product_key = service.create_license(
        plan=plan, expires_at=now[0] + timedelta(days=365)
    )
    return license_id, product_key, service.activate(product_key, device)


def test_signed_token_unlocks_only_issued_features(tmp_path: Path, issuer):
    _, key, now = issuer
    _, _, token = create_and_activate(issuer, PlanTier.STARTER)
    store = LicenseStore(
        tmp_path / "license.json",
        public_key_text=public_key_text(key),
        device=DEVICE_A,
        clock=lambda: now[0],
    )
    store.import_offline_token(token)
    assert store.state.is_valid(now=now[0])
    assert store.state.allows_output()
    assert not store.state.allows_pro_dfm()
    assert not store.state.allows_watermark_removal()


def test_token_tampering_and_wrong_device_are_rejected(tmp_path: Path, issuer):
    _, key, now = issuer
    _, _, token = create_and_activate(issuer)
    store = LicenseStore(
        tmp_path / "license.json",
        public_key_text=public_key_text(key),
        device=DEVICE_A,
        clock=lambda: now[0],
    )
    prefix, payload, signature = token.split(".")
    forged = ".".join((prefix, payload[:-1] + ("A" if payload[-1] != "A" else "B"), signature))
    with pytest.raises(LicenseTokenError):
        store.import_offline_token(forged)

    wrong_device = LicenseStore(
        tmp_path / "other.json",
        public_key_text=public_key_text(key),
        device=DEVICE_B,
        clock=lambda: now[0],
    )
    with pytest.raises(LicenseTokenError, match="另一台设备"):
        wrong_device.import_offline_token(token)


def test_expired_offline_token_is_rejected(tmp_path: Path, issuer):
    _, key, now = issuer
    token = sign_token(
        {
            "product": PRODUCT_ID,
            "license_id": "lic_expired",
            "plan": "starter",
            "features": ["photo_preview", "virtual_output"],
            "device_id": DEVICE_A,
            "expires_at": (now[0] + timedelta(days=30)).isoformat(),
            "token_expires_at": (now[0] - timedelta(seconds=1)).isoformat(),
        },
        key,
    )
    store = LicenseStore(
        tmp_path / "license.json",
        public_key_text=public_key_text(key),
        device=DEVICE_A,
        clock=lambda: now[0],
    )
    with pytest.raises(LicenseTokenError, match="联网刷新"):
        store.import_offline_token(token)


def test_device_limit_can_be_released(issuer):
    service, _, now = issuer
    license_id, product_key = service.create_license(
        plan=PlanTier.STARTER,
        expires_at=now[0] + timedelta(days=30),
        max_devices=1,
    )
    service.activate(product_key, DEVICE_A)
    with pytest.raises(PermissionError, match="设备数量"):
        service.activate(product_key, DEVICE_B)
    service.release_device(license_id, DEVICE_A)
    assert service.activate(product_key, DEVICE_B).startswith("FSS1.")


def test_expired_offline_lease_can_refresh_online(issuer):
    service, _, now = issuer
    _, _, token = create_and_activate(issuer)
    now[0] += timedelta(days=8)
    refreshed = service.refresh(token, DEVICE_A)
    assert refreshed.startswith("FSS1.")


def test_unsigned_legacy_json_never_unlocks(tmp_path: Path):
    path = tmp_path / "license.json"
    path.write_text(
        '{"tier":"pro","active":true,"dfm_enabled":true,"features":["virtual_output"]}',
        encoding="utf-8",
    )
    store = LicenseStore(path, device=DEVICE_A)
    assert not store.state.active
    assert not store.state.allows_output()
    assert store.enforce_startup_gate() == []


def test_client_cannot_self_upgrade(tmp_path: Path):
    store = LicenseStore(tmp_path / "license.json", device=DEVICE_A)
    with pytest.raises(RuntimeError, match="签名授权服务器"):
        store.set_tier(PlanTier.STUDIO)
    with pytest.raises(RuntimeError, match="客户端不能自行开通"):
        store.apply_usdt_payment_callback(amount_usdt=1499)
