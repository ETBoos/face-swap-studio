"""Signed local entitlement storage and online/offline activation."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from face_swap_studio.licensing.client import ActivationClient
from face_swap_studio.licensing.device import device_id
from face_swap_studio.licensing.plans import LicenseState, PlanTier
from face_swap_studio.licensing.token import LicenseTokenError, load_public_key, verify_token


def activation_configuration() -> tuple[str, str]:
    """Return server URL and pinned public key from env or packaged config."""
    url = os.environ.get("FSS_ACTIVATION_URL", "").strip()
    public_key = os.environ.get("FSS_LICENSE_PUBLIC_KEY", "").strip()
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "activation.json")
    candidates.append(Path(__file__).resolve().parents[3] / "activation.local.json")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(raw, dict):
            url = url or str(raw.get("activation_url") or "").strip()
            public_key = public_key or str(raw.get("license_public_key") or "").strip()
    return url.rstrip("/"), public_key


class LicenseStore:
    def __init__(
        self,
        path: Path,
        *,
        public_key_text: str | None = None,
        activation_url: str | None = None,
        device: str | None = None,
        clock: Callable[[], datetime] | None = None,
        enforce_gate: bool = True,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        configured_url, configured_key = activation_configuration()
        self.activation_url = (
            configured_url if activation_url is None else activation_url.rstrip("/")
        )
        self.public_key_text = (
            configured_key if public_key_text is None else public_key_text.strip()
        )
        self.device_id = device or device_id()
        self._clock = clock or (lambda: datetime.now(UTC))
        self.last_error = ""
        self.state = self._load()
        if enforce_gate:
            self.enforce_startup_gate()

    def _load(self) -> LicenseState:
        if not self.path.is_file():
            return LicenseState(device_id=self.device_id)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("license root must be an object")
            tier = PlanTier(raw.get("tier", PlanTier.STARTER.value))
            return LicenseState(
                tier=tier,
                seats=max(1, int(raw.get("seats", 1))),
                dfm_enabled=bool(raw.get("dfm_enabled", False)),
                active=bool(raw.get("active", False)),
                license_id=str(raw.get("license_id", "")),
                key_hint=str(raw.get("key_hint", "")),
                expires_at=str(raw.get("expires_at", "")),
                token_expires_at=str(raw.get("token_expires_at", "")),
                last_checked_at=str(raw.get("last_checked_at", "")),
                device_id=str(raw.get("device_id", self.device_id)),
                features=[x for x in raw.get("features", []) if isinstance(x, str)],
                signed_token=str(raw.get("signed_token", "")),
            )
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = f"授权文件无法读取：{exc}"
            return LicenseState(device_id=self.device_id)

    def save(self) -> None:
        data = asdict(self.state)
        data["tier"] = self.state.tier.value
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, self.path)

    def _apply_verified(self, token: str) -> None:
        public_key = load_public_key(self.public_key_text)
        payload = verify_token(
            token, public_key, expected_device_id=self.device_id, now=self._clock()
        )
        try:
            tier = PlanTier(payload["plan"])
        except (KeyError, ValueError) as exc:
            raise LicenseTokenError("授权套餐无效") from exc
        self.state = LicenseState(
            tier=tier,
            seats=max(1, int(payload.get("max_devices", 1))),
            dfm_enabled="professional_model" in payload["features"],
            active=True,
            license_id=str(payload["license_id"]),
            key_hint=str(payload.get("key_hint", "")),
            expires_at=str(payload["expires_at"]),
            token_expires_at=str(payload["token_expires_at"]),
            last_checked_at=self._clock().isoformat(),
            device_id=self.device_id,
            features=list(payload["features"]),
            signed_token=token.strip(),
        )
        self.last_error = ""
        self.save()

    def enforce_startup_gate(self) -> list[str]:
        """Verify every persisted entitlement; old editable JSON never grants access."""
        if not self.state.signed_token:
            was_active = self.state.active
            self.state = LicenseState(device_id=self.device_id)
            if was_active:
                self.last_error = "旧版本地授权不再有效，请使用产品密钥重新激活。"
                self.save()
                return ["unsigned_legacy_license"]
            return []
        try:
            self._apply_verified(self.state.signed_token)
            return []
        except LicenseTokenError as exc:
            self.last_error = str(exc)
            self.state.active = False
            self.state.features = []
            self.state.dfm_enabled = False
            self.save()
            return ["invalid_or_expired_signed_license"]

    def activate(self, product_key: str) -> None:
        if not self.activation_url:
            raise RuntimeError("此安装版本尚未配置授权服务器，请联系销售方。")
        response = ActivationClient(self.activation_url).activate(product_key, self.device_id)
        self._apply_verified(response["token"])

    def refresh(self) -> None:
        if not self.state.signed_token:
            raise RuntimeError("尚未激活")
        if not self.activation_url:
            raise RuntimeError("此安装版本尚未配置授权服务器")
        response = ActivationClient(self.activation_url).refresh(
            self.state.signed_token, self.device_id
        )
        self._apply_verified(response["token"])

    def import_offline_token(self, token: str) -> None:
        self._apply_verified(token)

    def deactivate_local(self) -> None:
        self.state = LicenseState(device_id=self.device_id)
        self.last_error = ""
        self.save()

    def status_text(self) -> str:
        if not self.state.is_valid(now=self._clock()):
            return "体验模式 · 输出需激活"
        expiry = self.state.expires_at[:10] if self.state.expires_at else ""
        return f"{self.state.tier.value.upper()} · 有效至 {expiry}"

    def set_tier(self, _tier: PlanTier) -> None:
        raise RuntimeError("套餐只能由签名授权服务器下发")

    def apply_usdt_payment_callback(self, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("付款确认必须在授权服务器完成，客户端不能自行开通")
