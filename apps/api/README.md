# Accord Python 后端

单进程 FastAPI + SQLite 后端，Python 3.9+。采用按业务组织的模块化单体；模型通信、业务状态和资料权限分开维护。

## 目录职责

```text
accord_api/
├── main.py                 # 应用工厂、初始化、路由和异常处理装配
├── app.py                  # 旧启动路径兼容入口
├── api/                    # HTTP 路由汇总、健康检查、中间件
├── modules/
│   ├── identity/           # 固定身份、兼容账号与登录会话；session.py 处理 Bearer / Cookie
│   ├── collaboration/      # 单聊、群聊、找本人、确认待办
│   ├── workspace/          # 文件夹、会话归档、资料绑定、页面状态查询
│   ├── knowledge/          # 文本导入、增量索引、跨会话检索、快照与只读工具
│   ├── agent_runs/         # 模型运行、停止重试、提示词和调用编排
│   ├── activity/           # 站内状态、可见工作、待办优先级
│   ├── topics/             # 独立探索、提交、统一公开、决策与交接
│   ├── preferences/        # 个人模型思考档位
│   └── permissions/        # 统一可见范围与历史边界
├── platform/
│   ├── ai/                 # 模型配置、错误、SSE 与工具调用协议
│   ├── db/                 # SQLite 连接、事务锁、集中初始化迁移
│   ├── commands.py         # 写操作幂等、版本检查
│   ├── config.py           # 与业务文件位置无关的数据路径
│   └── errors.py           # 业务异常；HTTP 层映射响应
└── jobs/                   # 后台派发、定时送达、启动中断恢复
```

模块内 `api.py` / `*_api.py` 接收请求、验证输入并注入登录身份；`schemas.py` 定义输入契约；`service.py` 及命名用例文件维护业务。跨用例复用的查询和序列化放 `repository.py`，不为每条 SQL 创建一个转发函数。资料创建和查询已统一放在 `knowledge`；页面聚合查询位于 `workspace/readmodel.py`。

`platform` 不依赖业务模块，业务模块不导入 `main`。模型 provider 通过传入的工具对象执行协议，不自行打开文件、连接数据库或决定共享权限。工具的唯一清单为 `knowledge/tool_schemas.py`。

## 启动与验证

以下命令从仓库根目录运行。服务端配置沿用根 `.env`，密钥不会进入前端。

```bash
.venv/bin/python tools/run-api.py
PYTHONPATH=apps/api .venv/bin/python -m unittest discover -s apps/api/tests -q
```

开发检查使用 `requirements-dev.txt` 中固定的 Ruff 版本，规则在 `pyproject.toml`。安装开发依赖后执行：

```bash
.venv/bin/python -m pip install -r apps/api/requirements-dev.txt
.venv/bin/ruff check apps/api/accord_api apps/api/tests/test_engineering.py
.venv/bin/ruff format --check apps/api/accord_api apps/api/tests/test_engineering.py
```

现有工作流测试保留原场景，新增 `test_engineering.py` 检查 49 个既有 API 路径的请求、响应声明和校验约束、模块依赖、导入无数据库副作用、资料来源及群聊权限。`fixtures/http-contract-v1.json` 来自重构前 OpenAPI；解析 `$ref` 后比较，忽略文件移动导致的内部模型命名和 `operationId`。

## 数据与运行约束

- 默认数据仍在根目录 `.local/workspace/data/pool.db`；`ACCORD_DATA_DIR` 可覆盖，按进程固定，启动后不能动态切库。
- 导入业务模块不建库；应用装配时集中执行可重复初始化。历史 43 张表保留兼容，旧原型的无调用业务函数已移除，不删除用户数据。
- `platform/db/migrations` 保留现有增量升级逻辑和历史资料文件导出。新增持久化变更在这里实现并补旧库升级测试；目前没有引入 Alembic。
- 一个 API 进程内最多两个模型执行线程。不要启用多个 Uvicorn worker / 多副本，当前调度不提供跨进程领取保证。
- 重启会把运行中的回答标记为中断，不自动付费重放。停止、重试、权限撤回和“Agent 完整回答后找本人”继续由服务端校验。
- 业务模块目前仍直接使用 SQLite 事务，这是有意保留的轻量实现；尚未引入 SQLAlchemy、Redis、Celery、对象存储或外部 MCP。

工程验收与后续内容接入边界见 [Python 后端工程化与上下文链路](../../docs/技术架构/2026-09-06-005-Python后端工程化与上下文链路-设计文档.md)。

## 内容索引

`knowledge/imports.py` 接收用户选择的 UTF-8 文件；`index.py` 消费事务变更队列，分段写入 SQLite FTS5；`retrieval.py` 在检索、来源展开、历史重用时检查原文与完整受众权限。聊天与会议复用 `person_context.py`。原文是事实源；索引不决定可见范围。变更与首次回填由 `knowledge_index.py` 迁移及现有后台线程维护，无需额外服务。

新增三个登录接口：`POST /api/knowledge/imports`、`GET /api/knowledge/search`、`GET /api/knowledge/chunks/{id}`。验收见 [内容接入与跨会话检索](../../docs/技术架构/2026-09-06-006-内容接入与跨会话检索-设计文档.md)，测试位于 `tests/test_knowledge_index.py`。
