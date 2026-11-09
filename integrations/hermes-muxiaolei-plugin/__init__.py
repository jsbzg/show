"""Hermes plugin muxiaolei 0.3 — full formal prepare/query surface; human confirm for writes."""
from __future__ import annotations

import json
import uuid
from typing import Any

from . import broker_ipc, capabilities, client, privacy

TOOLSET = "muxiaolei"
MOCK_TOOLS_ENABLED = __import__("os").environ.get("MUXIAOLEI_WRITE_MODE", "live").strip().lower() == "mock"
CONFIRM = "http://127.0.0.1:18085/"


def _ok(payload: dict) -> str:
    return json.dumps({"success": True, **payload}, ensure_ascii=False)


def _err(message: str, **extra) -> str:
    return json.dumps({"success": False, "error": message, **extra}, ensure_ascii=False)


def _reject_confirm_bypass(params: dict) -> str | None:
    for k in ("confirmed", "externalConfirmed", "verifyCode", "verify_code", "password", "csrf"):
        if k in params and params.get(k) not in (None, "", False):
            return _err(
                f"拒绝：禁止通过工具参数 {k} 代替人在确认页操作。请打开 {CONFIRM}",
                confirmationUrl=CONFIRM,
            )
    return None


def _rid(params: dict) -> str:
    return str(params.get("clientRequestId") or params.get("client_request_id") or uuid.uuid4())


def _ipc_result(raw: dict, *, summarize=None) -> str:
    if raw.get("error"):
        return _err(raw["error"], confirmationUrl=raw.get("confirmationUrl") or CONFIRM)
    result = raw.get("result") if isinstance(raw.get("result"), dict) else raw
    if summarize:
        return _ok(summarize(result))
    return _ok({"result": result})


def _prepare(ipc_name: str, args: dict, action_label: str) -> str:
    bad = _reject_confirm_bypass(args)
    if bad:
        return bad
    # strip bypass keys if empty
    clean = {k: v for k, v in args.items() if k not in ("confirmed", "externalConfirmed", "verifyCode", "verify_code", "password")}
    crid = clean.get("clientRequestId") or _rid(clean)
    clean["clientRequestId"] = crid
    if broker_ipc.mock_mode():
        body = {k: v for k, v in clean.items() if k != "clientRequestId"}
        raw = broker_ipc.mock_prepare(ipc_name.replace("prepare_", ""), crid, body)
        if raw.get("error"):
            return _err(raw["error"], confirmationUrl=CONFIRM)
        summary = privacy.summarize_prepare(raw.get("result"), action=action_label)
        summary["mode"] = "mock"
        summary["warning"] = "mock：未触达真实确认队列/财务；取消与过期仅 mock 有效"
        return _ok(summary)
    raw = broker_ipc.call_tool(ipc_name, clean)
    if raw.get("error"):
        return _err(raw["error"], confirmationUrl=raw.get("confirmationUrl") or CONFIRM)
    result = raw.get("result") if isinstance(raw.get("result"), dict) else raw
    summary = privacy.summarize_prepare(result, action=action_label)
    summary["mode"] = "live_prepare_only"
    summary["instruction"] = f"请用户打开 {CONFIRM} 核对后确认；模型不得声称已完成写入。"
    return _ok(summary)


# ----- reads -----
def handle_health(params: dict, **kwargs) -> str:
    del params, kwargs
    try:
        status, data = client._request("/upgrade-health")
        if status >= 400:
            return _err("业务服务离线或异常，请先启动木小垒 127.0.0.1:18080")
        return _ok({
            "reachable": True, "http_status": status,
            "app": (data or {}).get("app") if isinstance(data, dict) else None,
            "version": (data or {}).get("version") if isinstance(data, dict) else None,
        })
    except Exception as e:
        return _err(f"业务后端离线：{e}")


def handle_search_members(params: dict, **kwargs) -> str:
    del kwargs
    keyword = str(params.get("keyword") or "")
    page = max(1, int(params.get("page") or 1))
    size = max(1, min(int(params.get("size") or 5), 20))
    try:
        status, data = client.auth_request("/api/customers", query={"keyword": keyword, "page": page, "size": size})
        if status != 200 or not isinstance(data, dict) or not data.get("success"):
            return _err((data or {}).get("message") if isinstance(data, dict) else f"HTTP {status}")
        payload = data.get("data")
        if not isinstance(payload, dict):
            payload = {"items": payload if isinstance(payload, list) else []}
        summary = privacy.summarize_search(payload)
        summary["hint"] = "多结果时必须请用户确认唯一客户，禁止猜测后写入"
        return _ok(summary)
    except Exception as e:
        return _err(str(e))


def handle_get_balance(params: dict, **kwargs) -> str:
    del kwargs
    cid = params.get("customer_id")
    if cid in (None, ""):
        return _err("customer_id 必填")
    try:
        status, data = client.auth_request(f"/api/accounts/{cid}/balance")
        if status != 200 or not isinstance(data, dict):
            return _err((data or {}).get("message") if isinstance(data, dict) else f"HTTP {status}")
        if data.get("success") is False:
            return _err(data.get("message") or "余额查询失败")
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        return _ok(privacy.summarize_balance(cid, inner))
    except Exception as e:
        return _err(str(e))


def handle_capabilities(params: dict, **kwargs) -> str:
    del params, kwargs
    return _ok({
        "capabilities": capabilities.CAPABILITIES,
        "backlog_minimal": capabilities.BACKLOG_MINIMAL,
    })


def handle_confirmation_status(params: dict, **kwargs) -> str:
    del params, kwargs
    return _ipc_result(broker_ipc.call_tool("connection_status", {}), summarize=privacy.summarize_connection)


def handle_member_detail(params: dict, **kwargs) -> str:
    del kwargs
    cid = params.get("customer_id")
    parts = params.get("parts") or ["membership", "balance"]
    if not cid:
        return _err("customer_id 必填；客户不唯一时先 search")
    if not isinstance(parts, list) or not parts:
        return _err("parts 必填，如 membership,balance,profile,cards,history")
    return _ipc_result(
        broker_ipc.call_tool("member_detail", {"customerId": int(cid) if str(cid).isdigit() else cid, "parts": parts}),
        summarize=privacy.summarize_member_detail,
    )


def handle_catalog(params: dict, **kwargs) -> str:
    del params, kwargs
    return _ipc_result(broker_ipc.call_tool("catalog", {}), summarize=privacy.summarize_catalog)


def handle_appointments(params: dict, **kwargs) -> str:
    del kwargs
    date = params.get("date")
    if not date:
        return _err("date 必填，格式 YYYY-MM-DD")
    return _ipc_result(broker_ipc.call_tool("appointments", {"date": date}), summarize=privacy.summarize_appointments)


def handle_business_summary(params: dict, **kwargs) -> str:
    del kwargs
    start, end = params.get("start"), params.get("end")
    if not start or not end:
        return _err("start 与 end 必填（YYYY-MM-DD），用于日报/区间合计")
    return _ipc_result(
        broker_ipc.call_tool("business_summary", {"start": start, "end": end}),
        summarize=privacy.summarize_business_summary,
    )


def handle_operation_status(params: dict, **kwargs) -> str:
    del kwargs
    oid = params.get("operation_id") or params.get("operationId")
    if not oid:
        return _err("operation_id 必填")
    if broker_ipc.mock_mode():
        raw = broker_ipc.mock_status(str(oid))
        if raw.get("error"):
            return _err(raw["error"])
        return _ok(privacy.summarize_operation(raw.get("result")))
    return _ipc_result(
        broker_ipc.call_tool("operation_status", {"operationId": oid}),
        summarize=privacy.summarize_operation,
    )



def handle_mock_confirm(params: dict, **kwargs) -> str:
    """仅隔离 mock：标记 completed。不可用于生产；不可经参数切换。"""
    if not broker_ipc.mock_mode():
        return _err("muxiaolei_mock_confirm 仅隔离 mock 环境可用；生产确认必须在 18085 人工完成")
    # 禁止模型伪造 confirmed / 切写模式
    if (params or {}).get("confirmed") is True or str((params or {}).get("write_mode") or "").lower() == "live":
        return _err("禁止通过参数切换为生产确认或 confirmed=true")
    oid = (params or {}).get("operation_id")
    if not oid:
        return _err("需要 operation_id")
    raw = broker_ipc.mock_confirm(str(oid))
    if raw.get("error"):
        return _err(str(raw["error"]))
    return _ok(raw.get("result") or raw)



def handle_prepare_update_member_basic(params: dict, **kwargs) -> str:
    """准备更新姓名/电话（待 18085 确认）。禁止 confirmed=true。"""
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    cid = params.get("customer_id") or params.get("customerId")
    name, phone = params.get("name"), params.get("phone")
    if not cid or not name or not phone:
        return _err("customer_id、name、phone 必填")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(cid) if str(cid).isdigit() else cid,
        "name": str(name)[:80],
        "phone": str(phone)[:40],
    }
    if params.get("remark") is not None:
        args["remark"] = str(params.get("remark"))[:255]
    return _prepare("prepare_update_member_basic", args, "更新会员姓名电话（待确认）")


def handle_prepare_archive_member(params: dict, **kwargs) -> str:
    """准备软停用会员（待确认）。账务历史保留。禁止 confirmed=true。后端需 archive 接口。"""
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    cid = params.get("customer_id") or params.get("customerId")
    if not cid:
        return _err("customer_id 必填")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(cid) if str(cid).isdigit() else cid,
    }
    out = _prepare("prepare_archive_member", args, "停用会员软删除（待确认；账务保留）")
    # annotate pending deploy for live path clarity without claiming available
    if isinstance(out, str) and "pending_deploy" not in out:
        pass
    return out


def handle_mock_cancel(params: dict, **kwargs) -> str:
    del kwargs
    if not broker_ipc.mock_mode():
        return _err("仅 MUXIAOLEI_WRITE_MODE=mock 可用；真实取消请在 18085 确认页操作")
    oid = params.get("operation_id")
    if not oid:
        return _err("operation_id 必填")
    raw = broker_ipc.mock_cancel(str(oid))
    if raw.get("error"):
        return _err(raw["error"])
    return _ok(privacy.summarize_operation(raw.get("result")))


# ----- prepares -----
def handle_prepare_create_member(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    name, phone = params.get("name"), params.get("phone")
    if not name or not phone:
        return _err("name 与 phone 必填；禁止向生产插入测试会员——仅隔离环境或用户明确对象时 prepare")
    args = {"clientRequestId": _rid(params), "name": str(name)[:80], "phone": str(phone)[:40]}
    for k in ("remark", "membershipType", "membershipStart", "membershipEnd"):
        if params.get(k) is not None:
            args[k] = params[k]
    return _prepare("prepare_create_member", args, "新增会员（待确认）")


def handle_prepare_update_preferences(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    cid, hair, prefs = params.get("customer_id"), params.get("hair_color"), params.get("preferences")
    if not cid or hair is None or prefs is None:
        return _err("customer_id、hair_color、preferences 必填（非姓名电话；基本资料修改未开放）")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(cid) if str(cid).isdigit() else cid,
        "hairColor": str(hair)[:80],
        "preferences": str(prefs)[:1000],
    }
    return _prepare("prepare_update_profile", args, "更新发色/服务偏好（待确认）")


def handle_prepare_recharge(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    cid, amount = params.get("customer_id"), params.get("amount")
    if not cid or amount is None:
        return _err("customer_id 与 amount 必填；须用户已收款后再确认记账")
    try:
        amount = float(amount)
    except Exception:
        return _err("amount 须为数字且 > 0")
    if amount <= 0:
        return _err("amount 须 > 0")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(cid) if str(cid).isdigit() else cid,
        "amount": amount,
    }
    if params.get("note"):
        args["remark"] = str(params["note"])[:300]
    return _prepare("prepare_recharge", args, "会员充值记账（待确认已收款）")


def handle_prepare_checkout(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    cid, eid, items, pay = params.get("customer_id"), params.get("employee_id"), params.get("items"), params.get("payment_method")
    if not cid or not eid or not isinstance(items, list) or not items or not pay:
        return _err("customer_id、employee_id、items、payment_method 必填；模糊客户不可猜")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(cid) if str(cid).isdigit() else cid,
        "employeeId": int(eid) if str(eid).isdigit() else eid,
        "items": items,
        "paymentMethod": pay,
    }
    for src, dst in (("visit_card_id", "visitCardId"), ("appointment_id", "appointmentId"), ("commission_amount", "commissionAmount"), ("commission_note", "commissionNote")):
        if params.get(src) is not None:
            args[dst] = params[src]
    if params.get("note"):
        args["remark"] = str(params["note"])[:300]
    return _prepare("prepare_checkout", args, "开单结账（待确认）")


def handle_prepare_deduct(params: dict, **kwargs) -> str:
    params = dict(params)
    params["payment_method"] = "balance"
    return handle_prepare_checkout(params, **kwargs)


def handle_prepare_issue_card(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    need = ["customer_id", "service_type_id", "name", "paid_amount", "times", "start_date", "end_date"]
    if any(params.get(k) in (None, "") for k in need):
        return _err("customer_id,service_type_id,name,paid_amount,times,start_date,end_date 均必填")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(params["customer_id"]) if str(params["customer_id"]).isdigit() else params["customer_id"],
        "serviceTypeId": params["service_type_id"],
        "name": str(params["name"])[:80],
        "paidAmount": float(params["paid_amount"]),
        "times": int(params["times"]),
        "startDate": params["start_date"],
        "endDate": params["end_date"],
    }
    return _prepare("prepare_issue_card", args, "办理次卡并登记收款（待确认）")


def handle_prepare_appointment(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    need = ["customer_id", "employee_id", "service_type_id", "starts_at", "ends_at"]
    if any(params.get(k) in (None, "") for k in need):
        return _err("customer_id,employee_id,service_type_id,starts_at,ends_at 均必填")
    args = {
        "clientRequestId": _rid(params),
        "customerId": int(params["customer_id"]) if str(params["customer_id"]).isdigit() else params["customer_id"],
        "employeeId": params["employee_id"],
        "serviceTypeId": params["service_type_id"],
        "startsAt": params["starts_at"],
        "endsAt": params["ends_at"],
    }
    if params.get("note"):
        args["remark"] = str(params["note"])[:300]
    return _prepare("prepare_appointment", args, "新增预约（待确认）")


def handle_prepare_appointment_status(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    aid, date, status = params.get("appointment_id"), params.get("date"), params.get("status")
    if not aid or not date or status not in ("arrived", "cancelled", "no_show"):
        return _err("appointment_id、date、status(arrived|cancelled|no_show) 必填")
    args = {
        "clientRequestId": _rid(params),
        "appointmentId": aid,
        "date": date,
        "status": status,
    }
    return _prepare("prepare_appointment_status", args, "更新预约状态（待确认）")


def handle_prepare_reverse_order(params: dict, **kwargs) -> str:
    del kwargs
    bad = _reject_confirm_bypass(params)
    if bad:
        return bad
    oid, reason = params.get("order_id"), params.get("reason")
    if not oid or not reason or not str(reason).strip():
        return _err("order_id 与 reason 必填；金额/对象须用户逐次在确认页核对，模型不得自动执行")
    args = {"clientRequestId": _rid(params), "orderId": oid, "reason": str(reason)[:255]}
    return _prepare("prepare_reverse_order", args, "撤销订单并冲回/退款记账（待确认）")


def handle_delete_refused(params: dict, **kwargs) -> str:
    del params, kwargs
    return _err("功能未开放：无正式删除会员 API。缺口见 muxiaolei_capabilities.backlog_minimal", capability="not_open")


def register(ctx: Any) -> None:
    def T(name, desc, props, required, handler, emoji="🔌"):
        ctx.register_tool(
            name=name, toolset=TOOLSET,
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": props, "required": required}},
            handler=handler, description=desc[:80], emoji=emoji,
        )

    T("muxiaolei_health", "检查木小垒业务服务是否可达。只读。", {}, [], handle_health, "🩺")
    T("muxiaolei_search_members", "只读搜索会员（去标识）。多结果须用户确认唯一客户后再 prepare。",
      {"keyword": {"type": "string"}, "page": {"type": "integer"}, "size": {"type": "integer"}}, [], handle_search_members, "🔎")
    T("muxiaolei_get_balance", "只读查储值余额。",
      {"customer_id": {"type": "string"}}, ["customer_id"], handle_get_balance, "💳")
    T("muxiaolei_member_detail", "按需查已确定客户 membership/balance/profile/cards/history（需18085登录）。去标识摘要。",
      {"customer_id": {"type": "string"}, "parts": {"type": "array", "items": {"type": "string"}}},
      ["customer_id", "parts"], handle_member_detail, "👤")
    T("muxiaolei_catalog", "查询在用员工与服务项目编号/价格，供开单预约前校验。", {}, [], handle_catalog, "📋")
    T("muxiaolei_appointments", "查询某日预约列表（最多30，脱敏）。",
      {"date": {"type": "string", "description": "YYYY-MM-DD"}}, ["date"], handle_appointments, "📅")
    T("muxiaolei_business_summary", "查询日期范围收款/退款/充值/提成合计（非逐客流水明细）。",
      {"start": {"type": "string"}, "end": {"type": "string"}}, ["start", "end"], handle_business_summary, "📊")
    T("muxiaolei_operation_status", "查询 prepare 操作状态；uncertain 禁止重提，须人工查账。",
      {"operation_id": {"type": "string"}}, ["operation_id"], handle_operation_status, "⏱️")
    T("muxiaolei_confirmation_status", "确认页连接/登录状态。", {}, [], handle_confirmation_status, "🔐")
    T("muxiaolei_capabilities", "能力矩阵、真实话术工作流、缺口 backlog。", {}, [], handle_capabilities, "🧭")
    # 硬闸：只有显式 MUXIAOLEI_WRITE_MODE=mock 才注册 mock 工具；默认 live 永不暴露
    import os as _os
    _wm = (_os.environ.get("MUXIAOLEI_WRITE_MODE") or "live").strip().lower()
    if _wm == "mock" and broker_ipc.mock_mode():
        T("muxiaolei_mock_confirm", "仅 mock：确认待办（验证确认未写生产）。",
          {"operation_id": {"type": "string"}}, ["operation_id"], handle_mock_confirm, "🧪")
        T("muxiaolei_mock_cancel", "仅 mock：取消待确认操作（验证取消未执行）。",
          {"operation_id": {"type": "string"}}, ["operation_id"], handle_mock_cancel, "🧪")

    T("muxiaolei_prepare_update_member_basic", "准备更新会员姓名/电话（待18085确认）。禁止 confirmed=true。后端 PUT /api/customers/{id}。",
      {"client_request_id": {"type": "string"}, "customer_id": {"type": "string"}, "name": {"type": "string"}, "phone": {"type": "string"}, "remark": {"type": "string"}},
      ["client_request_id", "customer_id", "name", "phone"], handle_prepare_update_member_basic, "📝")
    T("muxiaolei_prepare_archive_member", "准备停用会员（软删除，保留账务）。待18085确认。需后端 archive 接口已部署。禁止 confirmed=true。",
      {"client_request_id": {"type": "string"}, "customer_id": {"type": "string"}},
      ["client_request_id", "customer_id"], handle_prepare_archive_member, "🗂️")
    T("muxiaolei_prepare_create_member", "准备新增会员（待18085确认）。禁止生产测试插入。禁止 confirmed=true。",
      {"name": {"type": "string"}, "phone": {"type": "string"}, "clientRequestId": {"type": "string"},
       "remark": {"type": "string"}, "membershipType": {"type": "string"},
       "membershipStart": {"type": "string"}, "membershipEnd": {"type": "string"}},
      ["name", "phone"], handle_prepare_create_member, "⏳")
    T("muxiaolei_prepare_update_preferences", "准备更新发色/偏好（非姓名电话）。待确认。",
      {"customer_id": {"type": "string"}, "hair_color": {"type": "string"}, "preferences": {"type": "string"},
       "clientRequestId": {"type": "string"}},
      ["customer_id", "hair_color", "preferences"], handle_prepare_update_preferences, "⏳")
    T("muxiaolei_prepare_recharge", "准备充值记账（请确认已收款）。待18085确认。非实际转账。",
      {"customer_id": {"type": "string"}, "amount": {"type": "number"}, "note": {"type": "string"},
       "clientRequestId": {"type": "string"}},
      ["customer_id", "amount"], handle_prepare_recharge, "⏳")
    T("muxiaolei_prepare_checkout", "准备开单结账（balance/cash/wechat/alipay/visit_card）。待确认；储值须确认页校验码。",
      {"customer_id": {"type": "string"}, "employee_id": {"type": "string"}, "items": {"type": "array"},
       "payment_method": {"type": "string"}, "visit_card_id": {"type": "string"},
       "appointment_id": {"type": "string"}, "commission_amount": {"type": "number"},
       "commission_note": {"type": "string"}, "note": {"type": "string"}, "clientRequestId": {"type": "string"}},
      ["customer_id", "employee_id", "items", "payment_method"], handle_prepare_checkout, "⏳")
    T("muxiaolei_prepare_deduct", "准备储值扣款开单（paymentMethod=balance）。待确认+校验码。",
      {"customer_id": {"type": "string"}, "employee_id": {"type": "string"}, "items": {"type": "array"},
       "appointment_id": {"type": "string"}, "note": {"type": "string"}, "clientRequestId": {"type": "string"}},
      ["customer_id", "employee_id", "items"], handle_prepare_deduct, "⏳")
    T("muxiaolei_prepare_issue_card", "准备办理次卡并登记收款。待确认。",
      {"customer_id": {"type": "string"}, "service_type_id": {"type": "string"}, "name": {"type": "string"},
       "paid_amount": {"type": "number"}, "times": {"type": "integer"},
       "start_date": {"type": "string"}, "end_date": {"type": "string"}, "clientRequestId": {"type": "string"}},
      ["customer_id", "service_type_id", "name", "paid_amount", "times", "start_date", "end_date"],
      handle_prepare_issue_card, "⏳")
    T("muxiaolei_prepare_appointment", "准备新增预约。待确认。",
      {"customer_id": {"type": "string"}, "employee_id": {"type": "string"}, "service_type_id": {"type": "string"},
       "starts_at": {"type": "string"}, "ends_at": {"type": "string"}, "note": {"type": "string"},
       "clientRequestId": {"type": "string"}},
      ["customer_id", "employee_id", "service_type_id", "starts_at", "ends_at"], handle_prepare_appointment, "⏳")
    T("muxiaolei_prepare_appointment_status", "准备更新预约状态 arrived|cancelled|no_show。待确认。",
      {"appointment_id": {"type": "string"}, "date": {"type": "string"}, "status": {"type": "string"},
       "clientRequestId": {"type": "string"}},
      ["appointment_id", "date", "status"], handle_prepare_appointment_status, "⏳")
    T("muxiaolei_prepare_reverse_order", "准备撤单冲回/退款记账。待用户逐次确认对象与金额；禁止自动执行。",
      {"order_id": {"type": "string"}, "reason": {"type": "string"}, "clientRequestId": {"type": "string"}},
      ["order_id", "reason"], handle_prepare_reverse_order, "⏳")
    T("muxiaolei_delete_customer", "永久删除未开放。请用 muxiaolei_prepare_archive_member 软停用（保留账务）。",
      {"customer_id": {"type": "string"}}, [], handle_delete_refused, "🚫")
