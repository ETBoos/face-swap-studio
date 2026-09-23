"""SQLite-backed license issuance used by the small activation service."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from face_swap_studio.licensing.plans import PLAN_CATALOG, PlanTier
from face_swap_studio.licensing.token import PRODUCT_ID, sign_token, verify_token

KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_product_key(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def product_key_hash(value: str) -> str:
    return hashlib.sha256(normalize_product_key(value).encode("ascii")).hexdigest()


def new_product_key() -> str:
    body = "".join(secrets.choice(KEY_ALPHABET) for _ in range(16))
    return "FSS-" + "-".join(body[i : i + 4] for i in range(0, 16, 4))


def _moment(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


class LicenseService:
    def __init__(
        self,
        database: Path,
        private_key: Ed25519PrivateKey,
        *,
        clock=None,
        offline_days: int = 7,
    ) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.private_key = private_key
        self.public_key = private_key.public_key()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.offline_days = max(1, min(30, int(offline_days)))
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS licenses (
                    id TEXT PRIMARY KEY,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_hint TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    max_devices INTEGER NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    customer_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS activations (
                    license_id TEXT NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
                    device_id TEXT NOT NULL,
                    first_activated_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (license_id, device_id)
                );
                """
            )

    def create_license(
        self,
        *,
        plan: PlanTier,
        expires_at: datetime,
        max_devices: int | None = None,
        customer_note: str = "",
    ) -> tuple[str, str]:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= self.clock():
            raise ValueError("expiry must be in the future")
        device_limit = max_devices or PLAN_CATALOG[plan].seats
        if not 1 <= device_limit <= 100:
            raise ValueError("max_devices must be 1..100")
        key = new_product_key()
        license_id = "lic_" + uuid.uuid4().hex
        with self._connect() as db:
            db.execute(
                "INSERT INTO licenses VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    license_id,
                    product_key_hash(key),
                    key[-4:],
                    plan.value,
                    expires_at.astimezone(UTC).isoformat(),
                    device_limit,
                    customer_note[:500],
                    self.clock().isoformat(),
                ),
            )
        return license_id, key

    def set_disabled(self, license_id: str, disabled: bool) -> None:
        with self._connect() as db:
            changed = db.execute(
                "UPDATE licenses SET disabled=? WHERE id=?", (int(disabled), license_id)
            ).rowcount
        if not changed:
            raise LookupError("license not found")

    def release_device(self, license_id: str, device_id: str) -> None:
        with self._connect() as db:
            changed = db.execute(
                "DELETE FROM activations WHERE license_id=? AND device_id=?",
                (license_id, device_id),
            ).rowcount
        if not changed:
            raise LookupError("activation not found")

    def _active_license(self, db: sqlite3.Connection, where: str, value: str):
        row = db.execute(f"SELECT * FROM licenses WHERE {where}=?", (value,)).fetchone()
        if row is None:
            raise PermissionError("产品密钥无效")
        if row["disabled"]:
            raise PermissionError("此授权已停用，请联系销售方")
        if self.clock() >= _moment(row["expires_at"]):
            raise PermissionError("产品授权已到期")
        return row

    def _bind(self, db: sqlite3.Connection, row, device_id: str) -> None:
        if not device_id.startswith("fss-") or len(device_id) != 68:
            raise ValueError("设备标识无效")
        existing = db.execute(
            "SELECT 1 FROM activations WHERE license_id=? AND device_id=?",
            (row["id"], device_id),
        ).fetchone()
        if existing is None:
            count = db.execute(
                "SELECT COUNT(*) FROM activations WHERE license_id=?", (row["id"],)
            ).fetchone()[0]
            if count >= row["max_devices"]:
                raise PermissionError("此密钥的设备数量已用完，请先解绑旧设备")
            db.execute(
                "INSERT INTO activations VALUES (?, ?, ?, ?)",
                (row["id"], device_id, self.clock().isoformat(), self.clock().isoformat()),
            )
        else:
            db.execute(
                "UPDATE activations SET last_seen_at=? WHERE license_id=? AND device_id=?",
                (self.clock().isoformat(), row["id"], device_id),
            )

    def _issue(self, row, device_id: str) -> str:
        plan = PlanTier(row["plan"])
        license_expiry = _moment(row["expires_at"])
        token_expiry = min(license_expiry, self.clock() + timedelta(days=self.offline_days))
        payload = {
            "version": 1,
            "product": PRODUCT_ID,
            "license_id": row["id"],
            "key_hint": row["key_hint"],
            "plan": plan.value,
            "features": sorted(PLAN_CATALOG[plan].features),
            "max_devices": int(row["max_devices"]),
            "device_id": device_id,
            "issued_at": self.clock().isoformat(),
            "expires_at": license_expiry.isoformat(),
            "token_expires_at": token_expiry.isoformat(),
        }
        return sign_token(payload, self.private_key)

    def activate(self, product_key: str, device_id: str) -> str:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._active_license(db, "key_hash", product_key_hash(product_key))
            self._bind(db, row, device_id)
            return self._issue(row, device_id)

    def refresh(self, token: str, device_id: str) -> str:
        payload = verify_token(
            token,
            self.public_key,
            expected_device_id=device_id,
            now=self.clock(),
            allow_expired_refresh_token=True,
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._active_license(db, "id", str(payload["license_id"]))
            active = db.execute(
                "SELECT 1 FROM activations WHERE license_id=? AND device_id=?",
                (row["id"], device_id),
            ).fetchone()
            if active is None:
                raise PermissionError("此设备已被解绑，请重新激活")
            self._bind(db, row, device_id)
            return self._issue(row, device_id)

    def list_licenses(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT l.*, COUNT(a.device_id) AS active_devices
                   FROM licenses l LEFT JOIN activations a ON a.license_id=l.id
                   GROUP BY l.id ORDER BY l.created_at DESC"""
            ).fetchall()
        return [dict(row) for row in rows]
