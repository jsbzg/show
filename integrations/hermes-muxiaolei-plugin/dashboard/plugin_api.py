"""Read-only REST for Hermes Desktop muxiaolei pane. Mounted at /api/plugins/muxiaolei/."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter()

_PKG = Path(__file__).resolve().parents[1]  # .../plugins/muxiaolei


def _load_pkg():
    """Load installed plugin modules by path (gateway may not have muxiaolei on sys.path)."""
    name = "muxiaolei"
    if name not in sys.modules:
        import types
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(_PKG)]
        sys.modules[name] = pkg
    mods = {}
    for mod_suffix, file in (
        ("client", "client.py"),
        ("privacy", "privacy.py"),
        ("capabilities", "capabilities.py"),
    ):
        mod_name = f"{name}.{mod_suffix}"
        if mod_name in sys.modules:
            mods[mod_suffix] = sys.modules[mod_name]
            continue
        path = _PKG / file
        spec = importlib.util.spec_from_file_location(mod_name, path)
        m = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = m
        assert spec.loader is not None
        spec.loader.exec_module(m)
        mods[mod_suffix] = m
    return mods["capabilities"], mods["client"], mods["privacy"]


@router.get("/capabilities")
async def get_capabilities():
    capabilities, _, _ = _load_pkg()
    return {"success": True, "capabilities": capabilities.CAPABILITIES}


@router.get("/health")
async def health():
    _, client, _ = _load_pkg()
    try:
        status, data = client._request("/upgrade-health")
        if status >= 400:
            return JSONResponse(
                {"success": False, "reachable": False, "http_status": status,
                 "message": "业务服务离线或异常，请先启动木小垒 (127.0.0.1:18080)"},
                status_code=503,
            )
        return {
            "success": True,
            "reachable": True,
            "http_status": status,
            "app": (data or {}).get("app") if isinstance(data, dict) else None,
            "version": (data or {}).get("version") if isinstance(data, dict) else None,
        }
    except Exception as e:
        return JSONResponse(
            {"success": False, "reachable": False, "message": f"业务后端离线：{e}"},
            status_code=503,
        )


@router.get("/members")
async def members(keyword: str = Query(""), page: int = Query(1, ge=1), size: int = Query(8, ge=1, le=20)):
    _, client, privacy = _load_pkg()
    try:
        status, data = client.auth_request(
            "/api/customers", query={"keyword": keyword, "page": page, "size": size},
        )
        if status != 200 or not isinstance(data, dict) or not data.get("success"):
            msg = (data or {}).get("message") if isinstance(data, dict) else f"HTTP {status}"
            return JSONResponse({"success": False, "error": msg}, status_code=502)
        payload = data.get("data")
        if not isinstance(payload, dict):
            payload = {"items": payload if isinstance(payload, list) else []}
        summary = privacy.summarize_search(payload)
        return {"success": True, **summary}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "offline": True}, status_code=503)


@router.get("/members/{customer_id}/balance")
async def member_balance(customer_id: str):
    _, client, privacy = _load_pkg()
    try:
        status, data = client.auth_request(f"/api/accounts/{customer_id}/balance")
        if status != 200 or not isinstance(data, dict):
            msg = (data or {}).get("message") if isinstance(data, dict) else f"HTTP {status}"
            return JSONResponse({"success": False, "error": msg}, status_code=502)
        if data.get("success") is False:
            return JSONResponse({"success": False, "error": data.get("message") or "失败"}, status_code=502)
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        return {"success": True, **privacy.summarize_balance(customer_id, inner)}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "offline": True}, status_code=503)
