# Accord

让 AI 先协调，重要的事由你拍板。

Accord 是 AlxOrigin Team 的黑客松项目：以“人 + 专属 Agent”为协作单元，让 Agent 代答日常问题、准备决策材料、衔接任务，减少对真人的打扰。

## 当前状态

2026-09-05：新版源码已进入 `apps/web` 与 `apps/api`。前端直接使用 Tutti UI System，已完成组件样板、亮暗工作台，以及“问 Agent → 找本人 → 本人确认 → 待办”的本地持久化流程。

[打开 Accord 工作台](http://127.0.0.1:5186) · [组件样板](http://127.0.0.1:5186/#gallery)。当前使用合成成员和共享资料；没有配置真实模型。身份选择仅用于本机演示，不能用于生产认证。

比赛截止：**2026-09-06 12:00（北京时间 / UTC+8）**。新版本实测见 [004 验收记录](docs/产品规划/2026-09-05-004-Tutti工作台接入-验收记录.md)。旧 MVP 的问题仍记录在 003，不代表旧副本已修复；会议、真实模型和双机访问尚未验收。

## 安装与运行

需要 Node 22+、Python 3.9+。在仓库根目录执行：

```bash
npm ci --ignore-scripts
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements.txt
python3 tools/dev-services.py start
```

macOS 使用当前用户域 launchd，服务名 `com.accord.web`、`com.accord.api`，分别监听 `127.0.0.1:5186`、`127.0.0.1:8786`。启动脚本可重复执行；`stop` 只卸载这两个服务，`status` 查看状态。日志分别为 `/tmp/accord-web.log`、`/tmp/accord-api.log`。不影响旧 MVP 和 Tutti 参考服务。

其他系统可在两个终端前台运行：

```bash
ACCORD_DEMO=1 PYTHONPATH=apps/api .venv/bin/python -m uvicorn accord_api.app:app --host 127.0.0.1 --port 8786
npm run dev
```

`npm run build` 生成 `apps/web/dist`。目前开发服务通过 Vite 代理 `/api`，没有配置生产部署；不要把仅前端 dist 当作完整协作服务。

默认数据位于 `.local/accord-data`。复制 `.env.example` 为 `.env` 后可设置数据目录及模型配置；launchd 启动脚本只读取列出的 Accord 变量。三个模型变量全部配置后才会调用 OpenAI 兼容接口，需重新启动服务；本轮未验收任一真实供应商。前台启动不会自动加载 `.env`，需由终端环境提供变量。

## 本地演示

1. 打开页面，选择林川；“找同事”中打开苏禾的 Agent，问工作台 UI 或联调资料。
2. 另开标签页选择苏禾，确认此时没有该请求。
3. 林川点击“找本人”，阅读共享范围、填写转交说明后提交。
4. 苏禾从“待我拍板”进入，补充判断，填写任务名称与结论并确认承担任务。
5. 双方“我的待办”可见同一条任务；仅苏禾可以标记完成。刷新后会话和任务仍保留。

这些姓名与资料为合成演示内容。状态每 3 秒轮询；独立标签页验收不等同于两台设备、正式账号或实时通知验收。

## 验证命令

```bash
npm run typecheck
npm run build
npm run check:ui
PYTHONPATH=apps/api .venv/bin/python -m unittest discover -s apps/api/tests -v
```

UI 规则见 [004-Accord UI / UX](harness/规范/004-AccordUIUX设计规范.md)，依赖及团队代码来源见 [第三方记录](THIRD_PARTY_NOTICES.md)。开发用响应式预览为 `tools/viewport-preview.html`，不在生产构建入口中。

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

## 已运行的本地参考

| 项目 | 使用方式 | 限制 |
| --- | --- | --- |
| 堡天 MVP | [打开本地页面](http://127.0.0.1:8765)；可选择“演示成员甲 / 乙” | 仅本机监听、合成数据、未配置模型 Key；界面里的 LAN 地址不代表已开双机访问 |
| Tutti | 本机 **Tutti Dev** 桌面窗口 | 已启动桌面与 daemon，未验收真实模型和 VM 多人云端能力 |

两个服务由当前用户域 launchd 管理，启动配置只在本地存在。

```bash
# 已加载时重启
launchctl kickstart -k gui/$(id -u)/com.accord.baotian-mvp
launchctl kickstart -k gui/$(id -u)/com.accord.tutti-reference

# 停止并卸载指定服务
launchctl bootout gui/$(id -u)/com.accord.baotian-mvp
launchctl bootout gui/$(id -u)/com.accord.tutti-reference

# 卸载后重新加载；已加载时不要重复 bootstrap
launchctl bootstrap gui/$(id -u) /Users/JCProjects/accord/.local/runtime/com.accord.baotian-mvp.plist
launchctl bootstrap gui/$(id -u) /Users/JCProjects/accord/.local/runtime/com.accord.tutti-reference.plist
```

MVP 日志：`/tmp/accord-baotian-mvp.log`；Tutti 日志：`/tmp/accord-tutti-reference.log`。上述是旧参考实例的配置与日志；新 Accord 的可复现安装入口见前文。

## 三个核心场景

1. 找同事：先问其 Agent；需要真人时再发起找人。
2. 开会：Agent 先收集信息形成简报，人决定谁参会，结论确认后落地。
3. 异步协作：共享成果与任务状态，Agent 建议分配，人确认责任人。

完整规则与验收口径见项目背景；比赛时间已确认，准确演示时长、赛题规则与“等材料”的具体清单仍需核对。
