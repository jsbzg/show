# Hermes 独立插件适配说明

## 已有正式 API → prepare（人工确认）

| 能力 | 后端 | 连接器 prepare | Hermes 工具 |
|------|------|----------------|-------------|
| 姓名电话 | `PUT /api/customers/{id}`（已有） | `prepare_update_member_basic`（本 PR 补丁） | `muxiaolei_prepare_update_member_basic` |
| 软删除 | `POST /api/customers/{id}/archive`（本 PR） | `prepare_archive_member` | `muxiaolei_prepare_archive_member` |
| 切换停用/恢复 | `PATCH .../toggle-status`（已有） | 不新增 | 可用原界面 |

`muxiaolei_mock_confirm` **仅**在 `MUXIAOLEI_WRITE_MODE=mock` 于插件加载时注册；运行时不可经模型参数切到生产确认。

后端未部署前：插件将 archive 标记为 `pending_deploy`，不伪称生产可用。
