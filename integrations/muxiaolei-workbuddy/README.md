# 木小垒 WorkBuddy / Hermes 连接器补丁（可选）

**本目录不是 jsbzg/show 运行时依赖。** 本地木小垒 WorkBuddyMCP 包当前**没有**可追踪的 git remote；
此补丁随 Show PR 交付，供部署到 `木小垒WorkBuddyMCP` 后启用 prepare 动作。

## 新增 prepare 动作（须 18085 人工确认；禁止 confirmed=true）

| 动作 | HTTP | 说明 |
|------|------|------|
| `prepare_update_member_basic` | `PUT /api/customers/{customerId}` | 姓名/电话/备注；依赖既有正式 API |
| `prepare_archive_member` | `POST /api/customers/{customerId}/archive` | 软停用；账务历史保留；需后端含本 PR 的 archive 接口 |

## 年卡

源码与试用说明明确：**年卡核销尚未启用**；连接器**不得猜测**年费/有效期/次数/余额处理。本补丁**不**新增年卡续期/核销 prepare。

## 安装

将 `core.actions.patch.mjs` 中的两个 `actions` 条目合并进现有 `core.mjs` 的 `actions` 对象，重启连接器。未部署升级后端前，`prepare_archive_member` 会在确认执行时 404 — 插件侧标记待部署。
