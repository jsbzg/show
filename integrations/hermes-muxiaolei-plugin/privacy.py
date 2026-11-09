"""De-identify member payloads before returning to the model."""
from __future__ import annotations

import hashlib
import re
from typing import Any


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) < 7:
        return "***"
    return digits[:3] + "****" + digits[-4:]


def _stable_ref(customer_id: Any) -> str:
    raw = str(customer_id).encode("utf-8")
    return "mxl_" + hashlib.sha256(raw).hexdigest()[:10]


def summarize_member(item: dict) -> dict:
    cid = item.get("id")
    return {
        "ref": _stable_ref(cid),
        "customer_id": cid,  # needed for follow-up balance tool; model may use it
        "status": item.get("status"),
        "membership_type": item.get("membershipType") or item.get("membership_type"),
        "phone_masked": _mask_phone(item.get("phone")),
        "has_name": bool(item.get("name")),
        # deliberately omit name, full phone, verifyCode, remark text
    }


def summarize_search(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {"items": [], "total": 0}
    items = payload.get("items")
    if items is None and isinstance(payload.get("data"), list):
        items = payload["data"]
    if not isinstance(items, list):
        items = []
    out_items = [summarize_member(x) for x in items if isinstance(x, dict)]
    total = payload.get("total")
    if total is None:
        total = payload.get("totalElements") or len(out_items)
    return {
        "count": len(out_items),
        "total": total,
        "page": payload.get("page") or payload.get("pageNum") or 1,
        "items": out_items,
    }


def summarize_balance(customer_id: Any, payload: Any) -> dict:
    bal = None
    if isinstance(payload, dict):
        bal = payload.get("balance")
        if bal is None and isinstance(payload.get("data"), dict):
            bal = payload["data"].get("balance")
    return {
        "ref": _stable_ref(customer_id),
        "customer_id": customer_id,
        "balance": bal,
        "currency_note": "CNY store credit (local)",
    }


def summarize_prepare(result: dict | None, *, action: str) -> dict:
    """De-identify prepare_* broker results for the model."""
    if not isinstance(result, dict):
        return {"action": action, "pending": False}
    out = {
        "action": action,
        "pending": True,
        "confirmationUrl": result.get("confirmationUrl") or "http://127.0.0.1:18085/",
        "operationId": result.get("operationId") or result.get("id"),
        "clientRequestId": result.get("clientRequestId"),
        "expiresIn": result.get("expiresIn") or result.get("ttl") or "约10分钟（以确认页为准）",
        "status": result.get("status") or "awaiting_human_confirm",
        "instruction": "请用户本人打开确认页审核；模型不得声称已扣款/已修改，也不得传 confirmed=true。",
    }
    # keep amount/type metadata if present without customer PII
    for k in ("amount", "paymentMethod", "label"):
        if k in result:
            out[k] = result[k]
    snap = result.get("snapshot") if isinstance(result.get("snapshot"), dict) else {}
    cust = snap.get("customer") if isinstance(snap.get("customer"), dict) else {}
    if cust.get("id") is not None:
        out["ref"] = _stable_ref(cust.get("id"))
        out["customer_id"] = cust.get("id")
        out["phone_masked"] = _mask_phone(cust.get("phone"))
        out["has_name"] = bool(cust.get("name"))
    return out


def summarize_connection(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {"loggedIn": False}
    return {
        "service": result.get("service"),
        "loggedIn": bool(result.get("loggedIn")),
        "confirmationUrl": result.get("confirmationUrl") or "http://127.0.0.1:18085/",
        "privacy": result.get("privacy"),
        # omit accountLabel (may contain identity)
    }


def summarize_operation(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {"pending": False}
    out = {
        "operationId": result.get("operationId") or result.get("id"),
        "action": result.get("action"),
        "status": result.get("status"),
        "expiresAt": result.get("expiresAt"),
        "message": result.get("message"),
        "confirmationUrl": result.get("confirmationUrl") or "http://127.0.0.1:18085/",
        "mode": result.get("mode"),
    }
    # strip nested PII snapshots if present
    return {k: v for k, v in out.items() if v is not None}


def summarize_catalog(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {"employees": [], "services": []}
    emps = result.get("employees") or []
    svcs = result.get("services") or []
    return {
        "employee_count": len(emps) if isinstance(emps, list) else 0,
        "service_count": len(svcs) if isinstance(svcs, list) else 0,
        "employees": [{"id": e.get("id"), "has_name": bool(e.get("name"))} for e in emps if isinstance(e, dict)][:50],
        "services": [{"id": s.get("id"), "price": s.get("price"), "has_name": bool(s.get("name"))} for s in svcs if isinstance(s, dict)][:50],
    }


def summarize_appointments(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {"count": 0, "items": []}
    rows = result.get("appointments") or []
    items = []
    for a in rows if isinstance(rows, list) else []:
        if not isinstance(a, dict):
            continue
        items.append({
            "id": a.get("id"),
            "status": a.get("status"),
            "startsAt": a.get("startsAt") or a.get("starts_at"),
            "has_customer": bool(a.get("customerId") or a.get("customer_id")),
        })
    return {"count": len(items), "limitedTo": result.get("limitedTo"), "items": items}


def summarize_business_summary(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {}
    keys = ["externalReceived","externalRefunded","rechargeReceived","visitCardReceived","commission","commissionUnset"]
    return {k: result.get(k) for k in keys if k in result}


def summarize_member_detail(result: dict | None) -> dict:
    if not isinstance(result, dict):
        return {}
    out = {}
    cust = result.get("customer") if isinstance(result.get("customer"), dict) else {}
    if cust.get("id") is not None:
        out["ref"] = _stable_ref(cust.get("id"))
        out["customer_id"] = cust.get("id")
        out["has_name"] = bool(cust.get("name"))
    if "balance" in result:
        out["has_balance"] = result.get("balance") is not None
        out["balance"] = result.get("balance")
    if isinstance(result.get("membership"), dict):
        m = result["membership"]
        out["membership_type"] = m.get("membershipType") or m.get("membership_type")
        out["status"] = m.get("status") or m.get("membershipStatus")
    if isinstance(result.get("profile"), dict):
        out["has_profile"] = True
    if isinstance(result.get("cards"), list):
        out["card_count"] = len(result["cards"])
    if isinstance(result.get("history"), list):
        out["history_count"] = len(result["history"])
    return out
