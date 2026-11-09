"""Call the existing 木小垒 18085 confirmation broker via local Unix IPC."""
from __future__ import annotations

import http.client
import json
import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any

CONFIRM_URL = "http://127.0.0.1:18085/"
_MOCK_STORE = Path(os.environ.get("MUXIAOLEI_MOCK_STORE") or "/tmp/muxiaolei-hermes-mock-ops.json")


def ipc_socket_path() -> Path:
    return Path(f"/private/tmp/muxiaolei-workbuddy-{os.getuid()}/bridge.sock")


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str):
        super().__init__("localhost")
        self._unix = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(20)
        self.sock.connect(self._unix)


def mock_mode() -> bool:
    return (os.environ.get("MUXIAOLEI_WRITE_MODE") or "live").strip().lower() == "mock"


def _load_mock() -> dict:
    if not _MOCK_STORE.exists():
        return {"ops": {}}
    try:
        return json.loads(_MOCK_STORE.read_text())
    except Exception:
        return {"ops": {}}


def _save_mock(data: dict) -> None:
    _MOCK_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def mock_prepare(action: str, client_request_id: str, args: dict) -> dict:
    """Idempotent mock pending ops; supports cancel/expire without real finance."""
    data = _load_mock()
    ops = data.setdefault("ops", {})
    now = time.time()
    # expire old
    for oid, o in list(ops.items()):
        if o.get("status") == "pending" and o.get("expires", 0) < now:
            o["status"] = "expired"
    existing = ops.get(client_request_id)
    fingerprint = json.dumps({"action": action, "args": args}, sort_keys=True, ensure_ascii=False)
    if existing:
        if existing.get("fingerprint") != fingerprint:
            return {"error": "此请求编号已用于不同内容", "confirmationUrl": CONFIRM_URL}
        return {"result": _public_mock(existing)}
    # cancel helper via args flag only in mock store tools — not user confirm
    op = {
        "id": client_request_id,
        "action": action,
        "args": {k: v for k, v in args.items() if k not in ("confirmed", "verifyCode")},
        "fingerprint": fingerprint,
        "created": now,
        "expires": now + 600,
        "status": "pending",
    }
    ops[client_request_id] = op
    _save_mock(data)
    return {"result": _public_mock(op)}


def mock_cancel(operation_id: str) -> dict:
    data = _load_mock()
    op = data.get("ops", {}).get(operation_id)
    if not op:
        return {"error": "没有此 mock 操作"}
    if op["status"] != "pending":
        return {"error": f"状态为 {op['status']}，不可取消"}
    op["status"] = "cancelled"
    _save_mock(data)
    return {"result": _public_mock(op)}


def mock_status(operation_id: str) -> dict:
    data = _load_mock()
    now = time.time()
    op = data.get("ops", {}).get(operation_id)
    if not op:
        return {"error": "没有此 mock 操作"}
    if op.get("status") == "pending" and op.get("expires", 0) < now:
        op["status"] = "expired"
        _save_mock(data)
    return {"result": _public_mock(op)}


def _public_mock(o: dict) -> dict:
    return {
        "operationId": o["id"],
        "action": o["action"],
        "status": o["status"],
        "expiresAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(o["expires"])),
        "confirmationUrl": CONFIRM_URL,
        "message": {
            "pending": "尚未执行（mock）：请到本机确认页核对；mock 不会产生真实财务",
            "cancelled": "已取消（mock），未执行",
            "expired": "已过期（mock），未执行",
            "completed": "已模拟确认（mock），未写入生产",
        }.get(o["status"], o["status"]),
        "mode": "mock",
    }



def mock_confirm(operation_id: str) -> dict:
    """Isolation-only: mark pending as completed without calling production finance APIs."""
    if not mock_mode():
        return {"error": "mock_confirm 拒绝：当前非 mock 模式"}
    data = _load_mock()
    op = data.get("ops", {}).get(operation_id)
    if not op:
        return {"error": "没有此 mock 操作"}
    if op["status"] != "pending":
        return {"error": f"状态为 {op['status']}，不可确认"}
    op["status"] = "completed"
    _save_mock(data)
    pub = _public_mock(op)
    pub["message"] = "已模拟确认（mock completed），未写入生产"
    return {"result": pub}

def call_tool(name: str, args: dict | None = None) -> dict[str, Any]:
    sock = ipc_socket_path()
    if not sock.exists():
        return {
            "error": "确认连接器未运行（缺少 bridge.sock）。请先启动 18085 确认页并登录授权。",
            "confirmationUrl": CONFIRM_URL,
        }
    body = json.dumps({"name": name, "args": args or {}}, ensure_ascii=False).encode("utf-8")
    conn = _UnixHTTPConnection(str(sock))
    try:
        conn.request(
            "POST", "/tool", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {"error": f"IPC 响应非 JSON HTTP {resp.status}", "confirmationUrl": CONFIRM_URL}
        if not isinstance(data, dict):
            return {"error": "IPC 响应格式异常", "confirmationUrl": CONFIRM_URL}
        if data.get("error"):
            return {"error": str(data["error"]), "confirmationUrl": CONFIRM_URL}
        return data if "result" in data else {"result": data}
    except Exception as e:
        return {"error": f"无法连接确认桥接：{e}", "confirmationUrl": CONFIRM_URL}
    finally:
        try:
            conn.close()
        except Exception:
            pass
