"""Stable privacy-preserving device identifier for license seat binding."""

from __future__ import annotations

import hashlib
import os
import platform
import uuid
from pathlib import Path


def _machine_source() -> str:
    override = os.environ.get("FSS_DEVICE_ID_SOURCE", "").strip()
    if override:
        return override
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                if value:
                    return f"windows:{value}"
        except OSError:
            pass
    for candidate in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = candidate.read_text(encoding="ascii").strip()
        except OSError:
            continue
        if value:
            return f"machine-id:{value}"
    return f"fallback:{platform.node()}:{uuid.getnode()}"


def device_id() -> str:
    digest = hashlib.sha256(
        ("face-swap-studio/device/v1/" + _machine_source()).encode("utf-8")
    ).hexdigest()
    return f"fss-{digest}"


def display_device_code(value: str | None = None) -> str:
    raw = value or device_id()
    return "-".join((raw[4:8], raw[8:12], raw[12:16])).upper()
