# Accord

让 AI 先协调，重要的事由你拍板。

Accord 是 AlxOrigin Team 的黑客松项目：以“人 + 专属 Agent”为协作单元，让 Agent 代答日常问题、准备决策材料、衔接任务，减少对真人的打扰。

## 当前状态

2026-09-05：新版在 `apps/web` 与 `apps/api` 中实现真实账号、邀请加入、个人会话、共享资料、找本人、本人确认任务与完成状态。前端沿用 Tutti UI System；当前模型已切换为 DeepSeek V4 Pro，默认最高思考（max），支持每个账号调整思考强度，已实际验证两轮资料读取与连续回答。

[打开 Accord 工作台](http://127.0.0.1:5186)。首次打开由使用者创建工作空间和自己的账号；没有预置成员或资料。当前为本机服务，团队公网部署、飞书 SSO、文件执行工具、会议和多 Agent 委托尚未完成。最新范围、缺口和证据见 [006 实施计划](docs/产品规划/2026-09-05-006-真实工作空间与模型接入-实施计划.md) 与 [006 验收记录](docs/产品规划/2026-09-05-006-真实工作空间与模型接入-验收记录.md)。004 记录保留为此前版本的历史验收。

## 安装与运行

需要 Node 22+、Python 3.9+。在仓库根目录执行：

```bash
npm ci --ignore-scripts
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.txt
cp .env.example .env
# 在本机 .env 填入模型配置，不提交真实密钥。
chmod 600 .env
python3 tools/dev-services.py start
```

已有 `.env` 时保留它，不要覆盖。macOS 使用当前用户域 launchd，服务名 `com.accord.web`、`com.accord.api`，分别监听 `127.0.0.1:5186`、`127.0.0.1:8786`。`stop` 只停止这两个服务，`status` 查看状态。日志位于 `/tmp/accord-web.log`、`/tmp/accord-api.log`。配置改动后执行 `start` 重启。

其他系统可分别前台运行：

```bash
.venv/bin/python tools/run-api.py
npm run dev
```

`tools/run-api.py` 仅在服务端加载根目录 `.env`。模型 key 不进入 Vite 进程、浏览器或 launchd 配置。`npm run build` 生成 `apps/web/dist`；完整服务仍需要 API，当前没有公网生产部署入口。

默认实际数据位于 `.local/workspace`；历史参考数据库保留在 `.local/accord-data`，不会自动迁入实际空间。隔离验收使用单独的数据目录和端口。SQLite、账号、会话和运行记录均在本地持久保存。

## 临时团队预览

2026-09-05 按 JC 要求切换为同一局域网访问，公网隧道已关闭。当前地址为 `http://192.168.18.225:5188/`，队友连接同一 Wi-Fi 后用各自账号进入真实工作空间。登录页和 WebSocket 热更新已实测；换网络后用下面的 start / status 命令更新地址。

```bash
# 启动当天局域网共享，不需要隧道软件或账号
python3 tools/preview-services.py start --lan
python3 tools/preview-services.py status
# 结束临时共享，本机开发服务不受影响
python3 tools/preview-services.py stop
```

`com.accord.preview` 由 launchd 托管，前端仅监听当前 Wi-Fi / 以太网的局域网 IP，后端继续只监听本机 8786。前端模块可以被浏览器加载，仓库文档、后端源码、密钥和数据库不在允许范围；首次管理员创建接口在共享入口禁用。默认 start 采用局域网模式，公网模式必须显式选择 `--public`。运行状态保存在 `.local/preview/status.json`，日志为 `/tmp/accord-preview.log`，不包含模型 key。

本次共享到 2026-09-06 00:00（北京时间）自动关闭。运行期间通过 caffeinate 防止空闲休眠，退出后自动释放；电脑仍须保持开机、联网，合盖或手动睡眠会影响访问。隧道进程重启可能更换地址。前端组件和样式通常热更新，部分变更会整页刷新；API 代码仍需重启后端，进行中的模型生成可能中断。Cloudflare Quick Tunnel 有并发限制且不支持 SSE，当前浏览器每秒轮询状态，不受该 SSE 限制影响。未来正式部署使用构建产物、云端 API 与持久数据卷，具体边界和验收见 [临时团队预览](docs/技术架构/2026-09-05-002-临时团队预览与正式部署-交接文档.md)。

## 使用流程

1. 创建工作空间，填写自己的姓名、邮箱和密码；后续用该账号登录。
2. 创建者在设置中生成邀请码。另一个成员在同一站点用自己的账号信息和邀请码加入，每个码仅使用一次，24 小时到期。邮箱目前用作登录标识，尚无邮件验证或找回密码。
3. 在工作台向 Agent 提问，或发布可向团队共享的资料。一般问题也会真实调用模型；没有共享依据时不编造团队事实。
4. “找同事”先进入对方的 Agent 通道；点击“找本人”后，才把当前记录交给对方。指定送达时间由服务端后台处理。
5. 对方阅读记录、填写结论并明确承担任务；双方可见该任务，仅负责人可以标记完成。

消息先落库，再进入后台生成队列。上游使用流式接口，网页每秒读取持久状态，支持停止与失败重试；当前不是浏览器 SSE 推送。单个 API 进程最多并行两个生成任务，每人同时一个，默认每日每人 200 次请求，按北京时间计算。重启中断的生成会标记失败，避免自动重复调用；已排队而尚未调用的请求继续处理。

模型使用 OpenAI 兼容协议，当前为 `deepseek-v4-pro`，请求显式启用 thinking，并默认使用 `reasoning_effort=max`。在右上角「工作空间设置 → 你的思考强度」选择轻量、深入或最高，账号偏好保存在服务端；修改影响下一次发送或重试，正在生成的回答使用发起时的档位。单次上游生成上限 65,536 tokens，整个回答默认限时 900 秒；最高档通常需要更多等待和用量。

根目录 `.env` 使用 JC 本次提供的 DeepSeek 凭据，不再使用 ChengziCV 的千问凭据；不会修改其他项目配置。缺少配置或供应商调用失败时显示实际错误，不返回伪造答案。页面用量只统计服务商实际回传的 token，中断未回报的消耗不估算为零。配置、思考与工具协议、实测记录见 [003 DeepSeek 模型与思考配置](docs/技术架构/2026-09-05-003-DeepSeek模型与思考配置-交接文档.md)。

## 验证命令

```bash
npm run typecheck
npm run build
npm run check:ui
node --test tools/preview-boundary.test.mjs tools/browser-capabilities.test.mjs
PYTHONPATH=apps/api .venv/bin/python -m unittest discover -s apps/api/tests -v
```

UI 规则见 [004-Accord UI / UX](harness/规范/004-AccordUIUX设计规范.md)，依赖及团队代码来源见 [第三方记录](THIRD_PARTY_NOTICES.md)。开发用响应式预览为 `tools/viewport-preview.html`；组件检查页为开发环境的 `#gallery`，两者不出现在产品导航中。

## 从这里开始

团队在线入口：[飞书 · 健城 / Accord](https://my.feishu.cn/drive/folder/JASqfAcOPlQh2LdTrkJcaM7fnmd)。后续 docs 的新增和实质更新在任务交付前同步，保留队友修改；规则见 [飞书文档同步规范](harness/规范/003-飞书文档同步规范.md)。

| 入口 | 用途 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | JC 的沟通习惯、项目边界、AI 协作入口 |
| [harness/索引.md](harness/索引.md) | 长期开发和归档规范 |
| [项目背景与需求基线](docs/产品规划/2026-09-05-001-项目背景与需求基线-交接文档.md) | 产品是什么、已有方案、版本差异 |
| [前期资料来源索引](docs/团队协作/2026-09-05-001-前期资料来源-调研记录.md) | 飞书与云端对话链接、读取范围 |
| [Tutti 参考评估](docs/竞品调研/2026-09-05-001-图蒂参考项目-调研记录.md) | 值得借鉴的机制及复用边界 |
| [初始化与后续任务](docs/产品规划/2026-09-05-002-项目初始化与后续工作-任务清单.md) | 已完成事项和进入实现前的工作 |
| [现有 MVP 验收记录](docs/产品规划/2026-09-05-003-现有原型评估与比赛收口-验收记录.md) | 运行结果、已复现问题、源码位置与限制 |
| [截止前实施计划](docs/产品规划/2026-09-05-003-现有原型评估与比赛收口-实施计划.md) | 范围、排期、演示脚本和 PPT 提纲 |
| [全部文档](docs/索引.md) | 按业务查找材料 |

## 目录

```text
accord/
├── AGENTS.md / README.md       # 协作与运行入口
├── apps/web/                  # React + Tutti UI System
├── apps/api/                  # FastAPI + SQLite / 行为测试
├── tools/                     # 启动、UI 检查与响应式验收
├── harness/                   # 长期规范
├── docs/                      # 背景、方案、计划与验收
├── screenshots/               # 本地验收图，不提交 Git
└── .local/                    # 本地数据、原始缓存与参考，不提交
```

## 独立参考

Tutti 源码位于 `/Users/JCProjects/tutti`。团队旧 MVP 的参考文件保存在 `.local/references`，其已有服务使用 `com.accord.baotian-mvp`，与本项目的实际数据和启动命令分开管理。本轮没有修改这些参考实例。

## 三个核心场景

1. 找同事：先问其 Agent；需要真人时再发起找人。
2. 开会：Agent 先收集信息形成简报，人决定谁参会，结论确认后落地。
3. 异步协作：共享成果与任务状态，Agent 建议分配，人确认责任人。

完整规则与验收口径见项目背景；比赛时间已确认，赛题规则与提交材料的具体清单仍需核对。
