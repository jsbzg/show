# Hermes 独立插件 muxiaolei（随 PR 快照）

本目录是 macOS 本机 `~/.hermes/plugins/muxiaolei` 的可审批安装快照，**不是** Show 后端运行时依赖。

## 本 PR 相对能力

- `muxiaolei_prepare_update_member_basic` → 连接器 `prepare_update_member_basic` → 既有 `PUT /api/customers/{id}`
- `muxiaolei_prepare_archive_member` → `prepare_archive_member` → 本 PR 新增 `POST /api/customers/{id}/archive`（**后端未部署前禁用/pending_deploy**）
- `muxiaolei_delete_customer`：永久删除拒绝，引导软归档
- `muxiaolei_mock_confirm` / `mock_cancel`：**仅**进程环境 `MUXIAOLEI_WRITE_MODE=mock` 时由 `register()` 注册；yaml 不宣称；运行时不可经模型参数/`confirmed=true`/临时 env 切到生产确认

## 安装

复制到目标机 `~/.hermes/plugins/muxiaolei` 后 `reload-plugins` 或重启 gateway。勿自动升级 Hermes 核心，勿部署未经验证业务包到门店。

## 年卡

见 `docs/ANNUAL_CARD_OPEN_QUESTIONS.md`；无明确产品规则前不开放续期/核销工具。
