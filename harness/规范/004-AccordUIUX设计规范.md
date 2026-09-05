# Accord UI / UX 设计规范

## 唯一基线

Accord 的界面基线是 `@tutti-os/ui-system@0.0.427`，通过 npm 公共包直接接入，精确版本记录于 `package-lock.json`。技术栈为 React 19、TypeScript、Vite 6、Tailwind CSS 4。源码参考 commit 为 `404a084f7780c475212f80d6563964c4bd7d8324`；该 checkout 与 npm 包不是相同版本，不宣称逐文件相同。

本规范适用于 Accord。ChengziCV 的品牌色、页面姿态和历史 UI 规则仍归其项目维护。本地 UI Skills 用于分析、实施和验收，不能覆盖这里已选定的视觉基线；不得同时套用多套配色、圆角与组件系统。

## 分层与导入

- 公共控件从 `@tutti-os/ui-system` 导入；图标从其 `/icons` 公共入口导入。先查组件元数据、类型与样板，不复制 shadcn 默认组件或手绘同义图标。
- 样式入口只在 `apps/web/src/styles.css` 引入一次公共 `styles.css`，保留 Tailwind 扫描公共 dist 的 `@source`。
- `features/workspace` 负责协作业务，`features/gallery` 提供组件验收面；`shared/ui.tsx` 只放跨页面组合。Dialog 中文关闭入口由公共 DialogContent、DialogClose 与 Button 组合。
- 业务页面不导入上游内部源码，不修改 node_modules，不反向污染 Tutti 参考 checkout。尚无需要提升到上游公共包的自研组件。

## 视觉规则

| 内容 | 已采用规则 |
| --- | --- |
| 颜色 | 用 `--background-*`、`--text-*`、`--line-*`、`--transparency-*` 等语义变量；产品源码不新增 hex / rgb / hsl 私有色板 |
| 主题 | 根元素 `data-theme="dark"` / `light`，两套主题均使用上游 Token；外观偏好存本机 |
| 字体 | 沿用上游 Lexend 与系统中文回退；根字号保持 16px，正文 13px，避免破坏以 rem 计算的组件尺寸 |
| 控件 | 默认 Button 实测高 32px、圆角 6px、字号 13px；语义 variant 表达强调度，状态附带文字 |
| 布局 | 桌面 52px 工具栏、224px 导航栏、弹性会话区、258px 上下文；768～1020px 隐藏上下文，760px 及以下导航收为抽屉 |
| 间距 | 以 4px 倍数组织面板与内容；图标光学间距、字号和上游组件内部尺寸保持原定义 |
| 容器 | 中性表面、细分隔线、稳定分栏；正文列表按行组织，避免为普通信息增加装饰卡片 |
| 图标 | 沿用 Tutti 图标，icon-only 动作提供中文 aria-label 与 tooltip；Accord 字标独立，不使用 Tutti 商标 |

不要用宽泛的 `.header span` / `button > span` 覆盖公共组件后代。业务文本采用明确选择器，Avatar、Badge 等保留自身样式契约。

## 业务交互

1. 找同事先进入对方 Agent 通道，页面明确当前接收者和模式。
2. 检索只读取已明确共享的资料；展示来源和“资料检索 / 模型回答 / 调用失败”。模型未配置时不表现为实时推理。
3. 找本人前展示将共享的会话范围；转交说明在双方记录中可见。指定送达时间必须带时区。
4. 由收到请求的本人填写结论、确认承担任务，服务端校验身份和状态，任务返回双方视角。模型文本不能代替该动作。
5. 任务完成独立于对话和确认；只有责任人明确标记完成。

## 状态与可用性

- 空态说明下一步；请求中禁用重复写入，显示进行中；失败保留明确重试入口。
- Enter 发送，Shift+Enter 换行；中文输入法合成期间 Enter 不发送。
- 弹窗支持 Escape、焦点约束和返回触发器；使用公共组件默认键盘行为。导航、发送和确认不用 hover 作为唯一入口。
- 窄屏收起无法展示的上下文按钮；共享资料仍可从“共享成果”进入。
- 尊重 `prefers-reduced-motion`；不新增会干扰阅读的循环动画。
- 当前身份选择仅供本地合成数据演示，不是生产认证方案；首版状态同步为每 3 秒轮询。

## 验收入口

`npm run typecheck`、`npm run build`、`npm run check:ui`。最后一项检查公共导入、颜色和图标边界，不能代替视觉验收。

浏览器检查暗色、亮色、空态、错误态、弹窗、来源菜单和主要协作路径。检查 390 / 768 / 1440 宽度；视口能力不可用时可用 `tools/viewport-preview.html` 的独立 iframe 验证响应式布局，记录它与真机触控验收的区别。

截图归档到 `screenshots/YYYY-MM-DD-主题/`，本轮证据与限制见 docs 中同主题 004 验收记录。后续任何视觉偏离先更新本规范并说明具体理由。
