# muxiaolei 0.3 验收摘录（隐私去标识）

## 已实测成功

### Desktop 正式 gateway（source=gui → platform=desktop，非 CLI -t）
- 句子：请只调用 muxiaolei_health 检查本机木小垒服务是否可达，然后用一句话报告 reachable 与 version。不要调用任何 MCP 工具，不要搜索，不要写文件。
- 证据：WS session.create source=gui；prompt.submit admission；agent.log platform=desktop；tool muxiaolei_health completed；助手回复「木小垒服务可达（reachable: true），version 为 1.2-merge。」；enabled_toolsets 含 muxiaolei。

### 鉴权后插件 API（X-Hermes-Gateway-Ticket / native-http，不绕过登录）
- GET /api/plugins/muxiaolei/health → 200 reachable:true version:1.2-merge
- GET /api/plugins/muxiaolei/capabilities → 200
- GET /api/plugins/muxiaolei/members?page=1&size=1 → 200（phone_masked=***）

### 隔离 mock 确认闭环（MUXIAOLEI_WRITE_MODE=mock，无生产写入）
- prepare→pending；同 id 幂等；异 fingerprint 冲突；cancel→cancelled；expire→expired；mock_confirm→completed；最终 status 查询。全部 mode=mock。

## 用户可打开入口
- Hermes Desktop 聊天（正式 gui session）
- Desktop 侧栏：~/.hermes/desktop-plugins/muxiaolei/plugin.js
- 插件 API：本机 gateway api_origin + /api/plugins/muxiaolei/*（需 ticket）
- 确认页：http://127.0.0.1:18085/（已测 HTTP 200；live 需真人登录）

## 缺项与最小下一步
1. Desktop/18085 GUI 画面：无远程用户 Mac GUI 正式工具（禁止 computerUse/AppleScript/读 App DB）。请用户本地打开 Hermes「木小垒」侧栏与 18085 确认页各截一张（可打码）。
2. 会员删除：源码无 DeleteMapping→真缺 API；需 forge 补接口。box 上 gh 已认证可作 go-ahead 后 CLI；Mac 无 gh。未获 go-ahead 不 clone/改 repo。
3. 姓名/电话：REST PUT /api/customers/{id} 有 name/phone；连接器未开放 prepare（仅发色/偏好）。需连接器/18085 动作后再适配，勿绕过确认页。
4. 年卡：StudioService「年卡核销尚未启用」；续期未开放。需产品规则+后端。
5. 真实升级包：未测。
6. mock_confirm 已写入独立插件并 reload-plugins。

## 代码工作 CLI
- box：gh 已安装且已登录（token 脱敏）；scopes gist/read:org/repo。
- 用户 Mac：gh 未安装。
