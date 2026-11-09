"""Capability matrix + natural-language workflows for muxiaolei Hermes plugin."""
from __future__ import annotations

VERSION = "0.3.0"
CONFIRM = "http://127.0.0.1:18085/"

# Formal connector actions (source: WorkBuddyMCP core.mjs actions + read tools)
CONNECTED_READ = {
    "health": {"tool": "muxiaolei_health", "via": "HTTP 18080 /upgrade-health", "status": "connected"},
    "search_members": {"tool": "muxiaolei_search_members", "via": "HTTP GET /api/customers", "status": "connected"},
    "get_balance": {"tool": "muxiaolei_get_balance", "via": "HTTP GET /api/accounts/{id}/balance", "status": "connected"},
    "member_detail": {"tool": "muxiaolei_member_detail", "via": "IPC member_detail → GET /api/studio/customers/{id}", "status": "connected_needs_18085_login"},
    "catalog": {"tool": "muxiaolei_catalog", "via": "IPC catalog → employees+services", "status": "connected_needs_18085_login"},
    "appointments_day": {"tool": "muxiaolei_appointments", "via": "IPC appointments", "status": "connected_needs_18085_login"},
    "business_summary": {"tool": "muxiaolei_business_summary", "via": "IPC business_summary → /api/studio/overview", "status": "connected_needs_18085_login"},
    "operation_status": {"tool": "muxiaolei_operation_status", "via": "IPC operation_status", "status": "connected_needs_18085_login"},
    "confirmation_status": {"tool": "muxiaolei_confirmation_status", "via": "IPC connection_status", "status": "connected"},
}

CONNECTED_PREPARE = {
    "update_member_basic": {"tool": "muxiaolei_prepare_update_member_basic", "via": "PUT /api/customers/{id}", "status": "prepare_ready_needs_connector_action"},
        "archive_member": {"tool": "muxiaolei_prepare_archive_member", "via": "POST /api/customers/{id}/archive", "status": "pending_deploy_backend_archive"},
        "create_member": {"tool": "muxiaolei_prepare_create_member", "ipc": "prepare_create_member", "status": "human_confirm"},
    "update_hair_preferences": {"tool": "muxiaolei_prepare_update_preferences", "ipc": "prepare_update_profile", "status": "human_confirm"},
    "recharge": {"tool": "muxiaolei_prepare_recharge", "ipc": "prepare_recharge", "status": "human_confirm"},
    "checkout": {"tool": "muxiaolei_prepare_checkout", "ipc": "prepare_checkout", "status": "human_confirm"},
    "deduct_balance": {"tool": "muxiaolei_prepare_deduct", "ipc": "prepare_checkout paymentMethod=balance", "status": "human_confirm"},
    "issue_card": {"tool": "muxiaolei_prepare_issue_card", "ipc": "prepare_issue_card", "status": "human_confirm"},
    "appointment": {"tool": "muxiaolei_prepare_appointment", "ipc": "prepare_appointment", "status": "human_confirm"},
    "appointment_status": {"tool": "muxiaolei_prepare_appointment_status", "ipc": "prepare_appointment_status", "status": "human_confirm"},
    "reverse_order": {"tool": "muxiaolei_prepare_reverse_order", "ipc": "prepare_reverse_order", "status": "human_confirm"},
}

NOT_OPEN = {
    "delete_customer_permanent": {"reason": "不提供永久删除；请用 prepare_archive_member 软停用"},
        "delete_customer": {"reason": "已改为软停用 archive；待后端/连接器部署"},
    "update_basic_profile_name_phone": {"reason": "已加 prepare_update_member_basic；连接器补丁见 Show PR integrations；部署前勿宣称生产可用"},
    "annual_card_renew_or_consume": {"reason": "StudioService：年卡核销尚未启用；连接器禁止猜测续期"},
    "password_change_sql_inventory_staff_crud": {"reason": "管理类功能未开放"},
    "model_auto_confirm": {"reason": "禁止 confirmed=true / 代填校验码"},
    "broadcast_message": {"reason": "无群发接口；本插件不开放"},
}

WORKFLOWS = [
    {
        "utterance": "查一下某会员，再看余额",
        "steps": ["muxiaolei_search_members", "muxiaolei_get_balance"],
        "confirm": False,
        "acceptance": "CLI/handler 已验；Desktop 聊天与侧栏页仍待 GUI 验收",
    },
    {
        "utterance": "给某位确定客户约明天某项目，准备好我确认",
        "steps": ["muxiaolei_catalog", "muxiaolei_search_members", "muxiaolei_prepare_appointment", "用户打开 18085 确认", "muxiaolei_operation_status"],
        "confirm": True,
        "acceptance": "prepare+mock 已验；真实确认闭环未对生产会员执行",
    },
    {
        "utterance": "用储值给某客户开某项目，金额明确",
        "steps": ["muxiaolei_catalog", "muxiaolei_search_members", "muxiaolei_get_balance", "muxiaolei_prepare_deduct 或 prepare_checkout", "18085 输校验码确认", "operation_status"],
        "confirm": True,
        "acceptance": "工具已接通；真实扣款确认未测",
    },
    {
        "utterance": "已收款，给某客户充值记账",
        "steps": ["muxiaolei_prepare_recharge", "18085 确认已收款", "operation_status"],
        "confirm": True,
        "acceptance": "工具已接通；非实际支付通道",
    },
    {
        "utterance": "查今天预约 / 查某日收款合计",
        "steps": ["muxiaolei_appointments", "muxiaolei_business_summary"],
        "confirm": False,
        "acceptance": "工具已注册；需 18085 已登录；Desktop GUI 未验",
    },
    {
        "utterance": "这笔单要冲回/退款记账",
        "steps": ["muxiaolei_prepare_reverse_order", "18085 逐次确认金额对象", "operation_status"],
        "confirm": True,
        "acceptance": "工具已接通；禁止自动执行；生产未测",
    },
]

CAPABILITIES = {
    "version": VERSION,
    "confirm_page": CONFIRM,
    "read": CONNECTED_READ,
    "write_prepare_only": CONNECTED_PREPARE,
    "not_open": NOT_OPEN,
    "workflows": WORKFLOWS,
    "isolation": {
        "plugin_dir": "~/.hermes/plugins/muxiaolei",
        "desktop_dir": "~/.hermes/desktop-plugins/muxiaolei",
        "outside_hermes_agent_tree": True,
        "upgrade_tested": False,
    },
    "desktop_ui": {
        "sidebar_label": "木小垒会员",
        "route": "/muxiaolei-members",
        "gui_accepted": False,
    },
}

BACKLOG_MINIMAL = [
    {
        "gap": "会员姓名/电话基本资料修改",
        "blocked_by": "业务系统未提供正式受支持写接口（连接器文档未开放）",
        "next": "下一阶段在木小垒业务仓库走正规 plan/PR：新增受控 PUT 资料接口 + 审计 + 确认页字段；本机不得偷偷改 repo",
        "not_allowed": ["直写库", "改角色伪开放", "任意 HTTP 代理", "模型自确认"],
    },
    {
        "gap": "删除会员",
        "blocked_by": "无正式 delete 动作/API",
        "next": "业务侧设计可恢复删除（软删/备份）+ 确认页；经授权代码工作流实现后再接入 prepare_delete",
        "not_allowed": ["批量永久删", "清库", "插件伪实现"],
    },
    {
        "gap": "Desktop 聊天/侧栏/18085 完整财务闭环验收",
        "blocked_by": "本执行器无 GUI 工具；禁止 Shell 驱 GUI / 读聊天库",
        "next": "用户在 Desktop：侧栏「木小垒会员」+ 对话触发 prepare + 18085 对隔离环境确认",
        "not_allowed": ["把 CLI -t 包装成 Desktop 成功"],
    },
    {
        "gap": "Notion 级多步串联（缺信息追问 + 可见结果卡片）",
        "blocked_by": "需 transcript 指令/工具结果富渲染与技能说明；非仅堆工具",
        "next": "可选：desktop TOOL_MEDIA / TRANSCRIPT_DIRECTIVE + 插件 skill 教模型工作流；仍经 18085 确认写",
        "not_allowed": ["绕过确认", "扩大 OS/Hermes 权限"],
    },
]
