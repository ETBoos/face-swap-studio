"""Bounded stdio framing for the isolated FaceFusion interpreter (stdlib only).

JSON headers precede optional BGR24 bytes. No pickle, image files or network
ports. A reader continuously drains this stream into one latest-frame slot.
"""
from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

PROTOCOL_VERSION = 1
MAX_HEADER_BYTES = 16 * 1024
MAX_FRAME_BYTES = 1920 * 1080 * 3
MAX_CONFIG_BYTES = 64 * 1024
_PREFIX = struct.Struct("!I")


class ProtocolError(ValueError):
    """Malformed, truncated, oversized or incompatible worker message."""


def _read_exact(stream: BinaryIO, amount: int, *, allow_eof: bool = False) -> bytes:
    parts = bytearray()
    while len(parts) < amount:
        chunk = stream.read(amount - len(parts))
        if not chunk:
            if allow_eof and not parts:
                return b""
            raise ProtocolError("FaceFusion worker returned a truncated message")
        parts.extend(chunk)
    return bytes(parts)


def _validate_header(header: dict[str, Any], payload_size: int) -> None:
    if header.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError("Unsupported FaceFusion worker protocol version")
    if header.get("type") not in {"ready", "frame", "error"}:
        raise ProtocolError("Unknown FaceFusion worker message type")
    if type(payload_size) is not int or not 0 <= payload_size <= MAX_FRAME_BYTES:
        raise ProtocolError("Invalid FaceFusion worker payload size")
    if header["type"] == "frame":
        width, height = header.get("width"), header.get("height")
        if (
            type(width) is not int or type(height) is not int
            or not 1 <= width <= 1920 or not 1 <= height <= 1080
            or payload_size != width * height * 3
            or header.get("format") != "bgr24"
            or not isinstance(header.get("meta"), dict)
        ):
            raise ProtocolError("Invalid BGR frame dimensions, format or metadata")
    elif payload_size != 0:
        raise ProtocolError("Non-frame messages cannot include image data")


def write_message(stream: BinaryIO, header: dict[str, Any], payload: bytes = b"") -> None:
    header = {**header, "protocol": PROTOCOL_VERSION, "payload_size": len(payload)}
    _validate_header(header, len(payload))
    encoded = json.dumps(header, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_HEADER_BYTES:
        raise ProtocolError("FaceFusion worker header is too large")
    stream.write(_PREFIX.pack(len(encoded)))
    stream.write(encoded)
    if payload:
        stream.write(payload)
    stream.flush()


def read_message(stream: BinaryIO) -> tuple[dict[str, Any], bytes] | None:
    prefix = _read_exact(stream, _PREFIX.size, allow_eof=True)
    if not prefix:
        return None
    size = _PREFIX.unpack(prefix)[0]
    if not 1 <= size <= MAX_HEADER_BYTES:
        raise ProtocolError("FaceFusion worker header is too large or empty")
    try:
        header = json.loads(_read_exact(stream, size))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Invalid FaceFusion worker JSON header") from exc
    if not isinstance(header, dict):
        raise ProtocolError("FaceFusion worker header must be an object")
    payload_size = header.get("payload_size")
    _validate_header(header, payload_size)
    return header, _read_exact(stream, payload_size)
