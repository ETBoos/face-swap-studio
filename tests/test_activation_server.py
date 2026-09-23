"""HTTP contract checks for the deployable activation service."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from face_swap_studio.licensing.client import ActivationClient
from face_swap_studio.licensing.server import handler_for, load_private_key_value
from face_swap_studio.licensing.service import LicenseService
from face_swap_studio.licensing.token import public_key_text, verify_token

DEVICE = "fss-" + "c" * 64


@pytest.fixture
def activation_server(tmp_path):
    key = Ed25519PrivateKey.generate()
    service = LicenseService(tmp_path / "licenses.sqlite3", key)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(service, "admin-test-token"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", key
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request_json(url, *, method="GET", payload=None, token=""):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read())


def test_admin_issues_key_and_desktop_activates(activation_server):
    url, signing_key = activation_server
    assert request_json(url + "/health") == (200, {"ok": True})
    status, issued = request_json(
        url + "/v1/admin/licenses",
        method="POST",
        token="admin-test-token",
        payload={"plan": "pro", "days": 30, "max_devices": 2, "note": "test"},
    )
    assert status == 201
    token = ActivationClient(url).activate(issued["product_key"], DEVICE)["token"]
    payload = verify_token(token, signing_key.public_key(), expected_device_id=DEVICE)
    assert payload["plan"] == "pro"
    assert "virtual_output" in payload["features"]


def test_admin_endpoint_rejects_missing_bearer(activation_server):
    url, _ = activation_server
    with pytest.raises(urllib.error.HTTPError) as caught:
        request_json(url + "/v1/admin/licenses")
    assert caught.value.code == 401


def test_private_key_environment_accepts_public_key_source():
    key = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    loaded = load_private_key_value(pem)
    assert public_key_text(loaded) == public_key_text(key)
