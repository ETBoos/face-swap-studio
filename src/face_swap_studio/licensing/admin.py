"""Owner CLI for key generation and license administration."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from face_swap_studio.licensing.plans import PlanTier
from face_swap_studio.licensing.server import load_private_key
from face_swap_studio.licensing.service import LicenseService
from face_swap_studio.licensing.token import public_key_text


def _write_private(path: Path, key: Ed25519PrivateKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    if os.name != "nt":
        path.chmod(0o600)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-keys", help="create the server signing key")
    init.add_argument("--private-key", type=Path, required=True)
    create = sub.add_parser("create", help="create a customer product key")
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--private-key", type=Path, required=True)
    create.add_argument("--plan", choices=[x.value for x in PlanTier], default="starter")
    create.add_argument("--days", type=int, default=365)
    create.add_argument("--max-devices", type=int)
    create.add_argument("--note", default="")
    listing = sub.add_parser("list", help="list licenses without revealing keys")
    listing.add_argument("--database", type=Path, required=True)
    listing.add_argument("--private-key", type=Path, required=True)
    disable = sub.add_parser("disable", help="disable or re-enable a license")
    disable.add_argument("--database", type=Path, required=True)
    disable.add_argument("--private-key", type=Path, required=True)
    disable.add_argument("license_id")
    disable.add_argument("--enable", action="store_true")
    release = sub.add_parser("release-device", help="release one occupied seat")
    release.add_argument("--database", type=Path, required=True)
    release.add_argument("--private-key", type=Path, required=True)
    release.add_argument("license_id")
    release.add_argument("device_id")
    args = parser.parse_args(argv)

    if args.command == "init-keys":
        if args.private_key.exists():
            raise SystemExit("Refusing to overwrite an existing private key")
        key = Ed25519PrivateKey.generate()
        _write_private(args.private_key, key)
        print("Private key created. Keep it outside the app and backups.")
        print("FSS_LICENSE_PUBLIC_KEY=" + public_key_text(key))
        return 0

    service = LicenseService(args.database, load_private_key(args.private_key))
    if args.command == "create":
        if not 1 <= args.days <= 3650:
            raise SystemExit("--days must be 1..3650")
        license_id, key = service.create_license(
            plan=PlanTier(args.plan),
            expires_at=datetime.now(UTC) + timedelta(days=args.days),
            max_devices=args.max_devices,
            customer_note=args.note,
        )
        print(json.dumps({"license_id": license_id, "product_key": key}, ensure_ascii=False))
    elif args.command == "list":
        print(json.dumps(service.list_licenses(), ensure_ascii=False, indent=2))
    elif args.command == "disable":
        service.set_disabled(args.license_id, not args.enable)
        print("ok")
    elif args.command == "release-device":
        service.release_device(args.license_id, args.device_id)
        print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
