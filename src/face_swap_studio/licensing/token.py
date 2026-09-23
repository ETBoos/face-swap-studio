"""Canonical Ed25519 license tokens; private keys never ship in the app."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

TOKEN_PREFIX = "FSS1"
PRODUCT_ID = "face-swap-studio"


class LicenseTokenError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise LicenseTokenError("授权凭证编码无效") from exc


def canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sign_token(payload: Mapping[str, Any], private_key: Ed25519PrivateKey) -> str:
    data = canonical_payload(payload)
    return f"{TOKEN_PREFIX}.{_b64(data)}.{_b64(private_key.sign(data))}"


def verify_token(
    token: str,
    public_key: Ed25519PublicKey,
    *,
    expected_device_id: str | None = None,
    now: datetime | None = None,
    allow_expired_refresh_token: bool = False,
) -> dict[str, Any]:
    try:
        prefix, encoded, signature = token.strip().split(".")
    except ValueError as exc:
        raise LicenseTokenError("授权凭证格式无效") from exc
    if prefix != TOKEN_PREFIX:
        raise LicenseTokenError("授权凭证版本不受支持")
    data = _unb64(encoded)
    try:
        public_key.verify(_unb64(signature), data)
    except InvalidSignature as exc:
        raise LicenseTokenError("授权签名无效") from exc
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LicenseTokenError("授权内容无效") from exc
    if not isinstance(payload, dict) or payload.get("product") != PRODUCT_ID:
        raise LicenseTokenError("授权不属于 FaceSwap Studio")
    if expected_device_id and payload.get("device_id") != expected_device_id:
        raise LicenseTokenError("授权属于另一台设备")
    current = now or datetime.now(UTC)
    for key, message in (
        ("expires_at", "产品授权已到期"),
        ("token_expires_at", "离线使用期限已到，请联网刷新授权"),
    ):
        try:
            limit = datetime.fromisoformat(str(payload[key]))
        except (KeyError, ValueError):
            raise LicenseTokenError("授权缺少有效期") from None
        if limit.tzinfo is None:
            limit = limit.replace(tzinfo=UTC)
        if current >= limit and not (key == "token_expires_at" and allow_expired_refresh_token):
            raise LicenseTokenError(message)
    features = payload.get("features")
    if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
        raise LicenseTokenError("授权功能列表无效")
    return payload


def load_public_key(value: str) -> Ed25519PublicKey:
    raw = value.strip().encode("ascii")
    if not raw:
        raise LicenseTokenError("发行版本尚未配置授权公钥")
    try:
        if b"BEGIN PUBLIC KEY" in raw:
            key = serialization.load_pem_public_key(raw)
        else:
            key = Ed25519PublicKey.from_public_bytes(_unb64(raw.decode("ascii")))
    except (ValueError, TypeError) as exc:
        raise LicenseTokenError("发行版本的授权公钥无效") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise LicenseTokenError("授权公钥类型无效")
    return key


def public_key_text(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return _b64(raw)
