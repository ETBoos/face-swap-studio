"""Minimal activation HTTP service. Put HTTPS in front of it in production."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.licensing.service import LicenseService


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("private key must be Ed25519")
    return key


def load_private_key_value(value: str) -> Ed25519PrivateKey:
    """Load a Railway secret stored as PEM text or base64-encoded PEM."""
    raw = value.strip().replace("\\n", "\n").encode("utf-8")
    if b"BEGIN PRIVATE KEY" not in raw:
        try:
            raw = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("FSS_LICENSE_PRIVATE_KEY is not valid PEM or base64") from exc
    key = serialization.load_pem_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("private key must be Ed25519")
    return key


def handler_for(service: LicenseService, admin_token: str = ""):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FaceSwapStudioLicense/1"

        def _reply(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._reply(HTTPStatus.OK, {"ok": True})
            elif self.path == "/v1/admin/licenses":
                if self._admin_allowed():
                    self._reply(HTTPStatus.OK, {"licenses": service.list_licenses()})
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _admin_allowed(self) -> bool:
            provided = self.headers.get("Authorization", "")
            expected = f"Bearer {admin_token}" if admin_token else ""
            if expected and secrets.compare_digest(provided, expected):
                return True
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "administrator token required"})
            return False

        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("invalid request size")
                data = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(data, dict):
                    raise TypeError("invalid JSON")
                if self.path == "/v1/activate":
                    token = service.activate(
                        str(data.get("product_key", "")), str(data.get("device_id", ""))
                    )
                elif self.path == "/v1/refresh":
                    token = service.refresh(
                        str(data.get("token", "")), str(data.get("device_id", ""))
                    )
                elif self.path == "/v1/admin/licenses":
                    if not self._admin_allowed():
                        return
                    days = int(data.get("days", 365))
                    if not 1 <= days <= 3650:
                        raise ValueError("days must be 1..3650")
                    license_id, product_key = service.create_license(
                        plan=PlanTier(str(data.get("plan", "starter"))),
                        expires_at=datetime.now(UTC) + timedelta(days=days),
                        max_devices=int(data["max_devices"])
                        if data.get("max_devices") is not None
                        else None,
                        customer_note=str(data.get("note", "")),
                    )
                    self._reply(
                        HTTPStatus.CREATED,
                        {"license_id": license_id, "product_key": product_key},
                    )
                    return
                elif self.path == "/v1/admin/disable":
                    if not self._admin_allowed():
                        return
                    service.set_disabled(
                        str(data.get("license_id", "")), bool(data.get("disabled", True))
                    )
                    self._reply(HTTPStatus.OK, {"ok": True})
                    return
                elif self.path == "/v1/admin/release-device":
                    if not self._admin_allowed():
                        return
                    service.release_device(
                        str(data.get("license_id", "")), str(data.get("device_id", ""))
                    )
                    self._reply(HTTPStatus.OK, {"ok": True})
                    return
                else:
                    self._reply(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._reply(HTTPStatus.OK, {"token": token})
            except PermissionError as exc:
                self._reply(HTTPStatus.FORBIDDEN, {"error": str(exc)})
            except LookupError as exc:
                self._reply(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (ValueError, TypeError, KeyError) as exc:
                self._reply(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception:  # noqa: BLE001 - keep internal details out of public HTTP responses
                self._reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "授权服务暂时不可用"})

        def log_message(self, format: str, *args) -> None:
            if os.environ.get("FSS_LICENSE_SERVER_LOG") == "1":
                super().log_message(format, *args)

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.environ.get("FSS_LICENSE_DATABASE", "/data/licenses.sqlite3")),
    )
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    parser.add_argument(
        "--offline-days", type=int, default=int(os.environ.get("FSS_OFFLINE_DAYS", "7"))
    )
    args = parser.parse_args(argv)
    private_key_value = os.environ.get("FSS_LICENSE_PRIVATE_KEY", "")
    if args.private_key:
        private_key = load_private_key(args.private_key)
    elif private_key_value:
        private_key = load_private_key_value(private_key_value)
    else:
        parser.error("set FSS_LICENSE_PRIVATE_KEY or pass --private-key")
    service = LicenseService(args.database, private_key, offline_days=args.offline_days)
    server = ThreadingHTTPServer(
        (args.host, args.port), handler_for(service, os.environ.get("FSS_ADMIN_TOKEN", ""))
    )
    print(f"FaceSwap Studio activation service listening on {args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
