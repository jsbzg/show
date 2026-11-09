"""HTTP client for 木小垒 local Show API (127.0.0.1 only)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE = "http://127.0.0.1:18080"
_LOOPBACK = re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?/?$", re.I)


def base_url() -> str:
    raw = (os.environ.get("MUXIAOLEI_BASE_URL") or DEFAULT_BASE).strip().rstrip("/")
    if not _LOOPBACK.match(raw + "/"):
        raise ValueError("安全限制：MUXIAOLEI_BASE_URL 只能是本机 127.0.0.1 / localhost")
    return raw


def _parse_body(raw: str) -> Any:
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return {"raw": raw[:300]}


def _request_curl(path: str, *, method: str, body: dict | None, token: str | None, query: dict | None, timeout: float):
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found")
    url = base_url() + path
    if query:
        qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None and v != ""})
        if qs:
            url = f"{url}?{qs}"
    cmd = [curl, "-sS", "-m", str(int(timeout)), "-X", method, "-H", "Accept: application/json", "-w", "\n%{http_code}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(body)]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
    out = proc.stdout.rsplit("\n", 1)
    raw = out[0] if len(out) == 2 else ""
    code = int(out[-1] if out else "0")
    return code, _parse_body(raw)


def _request_urllib(path: str, *, method: str, body: dict | None, token: str | None, query: dict | None, timeout: float):
    url = base_url() + path
    if query:
        qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None and v != ""})
        if qs:
            url = f"{url}?{qs}"
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "hermes-plugin-muxiaolei/0.1",
        "Connection": "close",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, _parse_body(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, _parse_body(raw)


def _request(
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    query: dict | None = None,
    timeout: float = 15.0,
) -> tuple[int, Any]:
    # Prefer curl on macOS: system Python urllib often gets RemoteDisconnected against this local Java server.
    if shutil.which("curl"):
        try:
            return _request_curl(path, method=method, body=body, token=token, query=query, timeout=timeout)
        except Exception:
            pass
    return _request_urllib(path, method=method, body=body, token=token, query=query, timeout=timeout)


def login() -> str:
    user = (os.environ.get("MUXIAOLEI_USERNAME") or "").strip()
    password = os.environ.get("MUXIAOLEI_PASSWORD") or ""
    if not user or not password:
        raise RuntimeError(
            "缺少 MUXIAOLEI_USERNAME / MUXIAOLEI_PASSWORD。"
            "请写入 ~/.hermes/.env（chmod 600），勿把密码放进对话。"
        )
    status, data = _request(
        "/api/auth/login",
        method="POST",
        body={"username": user, "password": password},
    )
    if status != 200 or not isinstance(data, dict) or not data.get("success"):
        msg = data.get("message") if isinstance(data, dict) else None
        raise RuntimeError(msg or f"登录失败 HTTP {status}")
    token = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("token")
    if not token:
        raise RuntimeError("登录响应无 token")
    return str(token)


def auth_request(path: str, *, method: str = "GET", body: dict | None = None, query: dict | None = None):
    token = login()
    status, data = _request(path, method=method, body=body, token=token, query=query)
    if status == 401:
        token = login()
        status, data = _request(path, method=method, body=body, token=token, query=query)
    return status, data
