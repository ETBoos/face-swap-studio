"""Small HTTPS client for the FaceSwap Studio activation service."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ActivationClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        parsed = urllib.parse.urlparse(self.base_url)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if (
            parsed.scheme != "https"
            and not local
            and os.environ.get("FSS_ALLOW_INSECURE_ACTIVATION") != "1"
        ):
            raise ValueError("授权服务器必须使用 HTTPS")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error")
            except (ValueError, UnicodeError):
                detail = None
            raise RuntimeError(detail or f"授权服务器返回错误 {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"无法连接授权服务器：{exc}") from exc
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError("授权服务器返回了无效数据") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("token"), str):
            raise TypeError("授权服务器没有返回有效凭证")
        return raw

    def activate(self, product_key: str, device_id: str) -> dict[str, Any]:
        key = "-".join(product_key.strip().upper().split())
        if len(key) < 12:
            raise ValueError("请输入完整的产品密钥")
        return self._post("/v1/activate", {"product_key": key, "device_id": device_id})

    def refresh(self, token: str, device_id: str) -> dict[str, Any]:
        return self._post("/v1/refresh", {"token": token, "device_id": device_id})
