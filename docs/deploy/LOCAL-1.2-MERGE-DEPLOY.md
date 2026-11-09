# 本机 1.2-merge 部署计划（禁止覆盖上游/旧功能）

## 仓库归属结论
- `jsbzg/show` = 第三方开源上游（owner=jsbzg，非用户）
- 用户 fork = `davarana0-pixel/show`
- 正式门店运行 = `木小垒合并升级包` JAR `muxiaolei-upgrade.jar` version `1.2-merge`（UpgradeServerMain）
- **禁止**用上游 PR 构建替换正式包；**禁止** merge 上游第三方仓

## 变更范围
仅在升级包 `source/` 增加 archive API（无 schema migration），对齐 Hermes/WorkBuddy prepare。
年卡核销/续期：**不实现**（试用说明明确尚未启用）。

## 步骤
1. `data_guard.py backup-active`（受支持备份）
2. 备份当前 `build/muxiaolei-upgrade.jar` 到 `build/muxiaolei-upgrade.jar.bak-<ts>`
3. 源码打补丁 → javac/jar 构建（主类 UpgradeServerMain）
4. 隔离 fixture 测 archive/PUT（不读生产 DB）
5. `manage.py status production` + `/upgrade-health`；确认无进行中业务（确认页空闲）
6. `manage.py stop production` → 换 jar → `manage.py start production`
7. 验收：upgrade-health、只读查询；不做生产写入
8. 失败：还原 bak jar 并 start
