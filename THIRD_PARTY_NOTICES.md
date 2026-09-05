# 第三方与团队来源

## AI Memory（独立参考）

- 来源：https://github.com/akitaonrails/ai-memory.git。
- 参考 commit：`a2fd58ccc5ff736274035e660846c831a0fd0e86`，上游声明 MIT，保留原仓库 LICENSE。
- 当前仅克隆与静态研究，没有把源码或二进制纳入 Accord 产品，也未安装全局 hooks、注册 MCP 或读取私人会话。未来实际分发时须记录所采用版本及随附许可。

## Tutti UI System

- 来源：https://github.com/tutti-os/tutti ，源码参考 commit `404a084f7780c475212f80d6563964c4bd7d8324`，路径 `packages/ui/system`。
- 实际依赖：`@tutti-os/ui-system@0.0.427`；通过公共导出使用组件、图标、字体与样式，不代表 npm 包与上述源码 commit 完全相同。
- npm 包随附 Apache-2.0 `LICENSE` 与第三方 `NOTICE`，副本保存在 `apps/web/public/licenses/tutti-ui-system/`，构建会保留。字体许可在 `apps/web/public/licenses/lexend/`（若包提供）。
- Accord 页面、中文文案与业务逻辑由本项目实现；未修改上游组件源码，也未使用 Tutti 产品标志冒充官方产品。

## 团队原型存储层

`apps/api/accord_api/store.py` 基于团队飞书提供的堡天 MVP `server/store.py`。原文件 SHA-256 为 `5401f18fd2d42a274686dcd1bdf979ba81f0c21b1de28c8624c2f523192e2000`。

改动：存储路径改为 `ACCORD_DATA_DIR` / `.local/accord-data`，允许创建父目录；时间采用带 UTC 时区的 ISO 表达；可重入锁用于组合事务。新应用未挂载旧原型的 HTTP / WebSocket 路由、模型写状态流程或全量快照。

团队原型没有在本轮提供独立的开源许可声明，因此不为其擅自指定第三方开源许可；公开发布时应沿用团队确认的代码归属和发布许可。
