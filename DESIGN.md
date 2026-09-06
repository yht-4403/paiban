---
name: 拍办
description: 可信、克制而灵动的人机协作工作台
colors:
  primary: "oklch(0.55 0.21 268)"
  primary-pressed: "oklch(0.49 0.21 268)"
  primary-soft: "oklch(0.95 0.035 268)"
  canvas: "oklch(0.965 0.009 268)"
  surface: "oklch(0.995 0.003 268)"
  panel: "oklch(0.95 0.012 268)"
  ink: "oklch(0.25 0.03 268)"
  ink-muted: "oklch(0.47 0.025 268)"
  line: "oklch(0.89 0.015 268)"
  spark-sun: "oklch(0.88 0.17 95)"
  spark-coral: "oklch(0.68 0.19 30)"
  spark-violet: "oklch(0.58 0.20 305)"
  success: "oklch(0.58 0.16 150)"
  danger: "oklch(0.56 0.21 25)"
typography:
  brand:
    fontFamily: "Lexend Variable, PingFang SC, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 650
    lineHeight: 1
    letterSpacing: "-0.08em"
  headline:
    fontFamily: "Lexend Variable, PingFang SC, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Lexend Variable, PingFang SC, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "Lexend Variable, PingFang SC, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  tag: "4px"
  control: "6px"
  surface: "12px"
  signal: "14px"
  composer: "16px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 12px"
  button-primary-hover:
    backgroundColor: "{colors.primary-pressed}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  input:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    height: "32px"
    padding: "0 10px"
  composer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.composer}"
    padding: "6px 0 0"
---

# Design System: 拍办

## 1. Overview

**Creative North Star: “可信任协作控制台”**

拍办的大部分时间应像一张干净、可靠的工作台：品牌色轻微渗入中性背景，栏位边界稳定，正文对比清楚。视觉变化服务于“现在是谁在回复、哪些资料可见、哪一步需要人拍板”，不为 AI 身份增加无意义的奇观。

参考 Kimi 的是安静表面与聚焦输入的节奏，不复制它的品牌资产和界面结构。拍办的识别来自蓝紫与珊瑚色交扣的双圆标识、冷中性分层，以及黄色只在共同结论处出现的一点“协作火花”。Logo 本身不放中文或英文，产品名“拍办”在界面中独立排版。

**Key Characteristics:**

- 亮色默认、暗色完整可用。
- 三层结构清楚：导航面、内容面、上下文面。
- 主操作蓝紫实色，其余操作按后果逐级降噪。
- 高饱和色面积不超过单屏视觉重量的约 10%。
- 以 4px 为基准的紧凑产品密度。

## 2. Colors

品牌冷蓝紫提供专业与确定性；黄、珊瑚和紫只做状态、身份和空态中的短促火花。

### Primary

- **拍办蓝** (`oklch(0.55 0.21 268)`): 主按钮、发送、焦点、当前选择。
- **Cobalt Soft** (`oklch(0.95 0.035 268)`): 选中行、Agent 回答和信息提示的低强调背景。

### Secondary

- **Signal Sun** (`oklch(0.88 0.17 95)`): 非文字装饰、待处理提示的辅助标记。
- **Action Coral** (`oklch(0.68 0.19 30)`): 新提醒和需要注意的协作火花。
- **Decision Violet** (`oklch(0.58 0.20 305)`): 会议、群组或决策状态的小面积身份色。

### Neutral

- **Cool Canvas** (`oklch(0.965 0.009 268)`): 应用外层和导航背景。
- **Clear Surface** (`oklch(0.995 0.003 268)`): 主内容与输入面。
- **Quiet Panel** (`oklch(0.95 0.012 268)`): 侧栏、字段和次级分组。
- **Trust Ink** (`oklch(0.25 0.03 268)`): 正文与关键标签。
- **Muted Ink** (`oklch(0.47 0.025 268)`): 次级信息；不用于需要高对比的占位文案。

**The Rare Color Rule.** 蓝紫只标记当前行动；三种协作火花不得同时成为大面积背景，也不得仅靠颜色表达业务状态。

## 3. Typography

**Brand Mark:** 蓝紫与珊瑚色双圆互扣，中央黄色节点表示共同结论；透明背景、无文字。

**Body Font:** Lexend Variable，中文回退为 PingFang SC 和系统无衬线。

**Character:** 图形标识提供协作识别，产品界面保持单一无衬线系统，标签熟悉、数字稳定、中文正文清楚。

### Hierarchy

- **Brand Name** (650, 17–32px, 1): 仅用于登录和侧栏中与图形标识并列的“拍办”。
- **Headline** (600, 20–24px, 1.35): 页面主标题和首次空态标题。
- **Title** (500–600, 14–16px, 1.45): 面板、任务与对话标题。
- **Body** (400, 13–14px, 1.65–1.8): 消息、证据和说明，长文限制在约 70ch。
- **Label** (500, 11–12px, 1.4): 状态、按钮和元数据；不使用全大写字距装饰。

**The Product Type Rule.** 品牌名与产品界面统一使用无衬线字体，不在按钮、导航、数据或状态标签中另加展示字体。

## 4. Elevation

系统以色调分层和细分隔线为主。静止列表不使用阴影；登录卡、浮层和聚焦输入区才获得低到中等结构性阴影。暗色主题通过表面明度而非重阴影建立深度。

### Shadow Vocabulary

- **Control lift** (`0 1px 2px oklch(0.25 0.03 268 / 0.08)`): 分段控件当前项。
- **Composer lift** (`0 2px 8px oklch(0.25 0.03 268 / 0.08)`): 主输入区。
- **Window lift** (`0 12px 32px oklch(0.25 0.03 268 / 0.12)`): 登录卡和真正浮于页面之上的弹层；不用于应用最外层工作台。

**The Flat-by-default Rule.** 普通信息靠间距、表面和分隔线分组；阴影只说明真实层级或聚焦状态。

## 5. Components

### Buttons

- **Shape:** 6px 圆角，默认高 32px；移动端主要路径扩大到至少 44px 触控区域。
- **Primary:** 拍办蓝实色配高对比前景，仅用于提交、发送、创建与明确放行。
- **Hover / Focus:** hover 加深；focus 使用 2px 品牌色焦点环；active 仅 1px 位移。
- **Secondary / Ghost:** 次级表面或透明背景，避免与主操作争夺注意力。

### Chips

- **Style:** 4–6px 圆角，浅色语义背景配同色深文本。
- **State:** 状态必须带文字；选中项可增加图标或实心标记。

### Cards / Containers

- **App shell:** 直接铺满浏览器视口，不用外边距、圆角或整窗阴影模拟“大卡片”。
- **Corner Style:** 普通容器 12px，输入区最多 16px。
- **Background:** 主内容 Clear Surface，侧栏 Quiet Panel。
- **Shadow Strategy:** 普通列表无阴影；确认、登录或浮层按 Elevation 使用。
- **Border:** 细线只用于真实分区；不同时叠加宽软阴影。
- **Internal Padding:** 使用 12 / 16 / 24px，不使用任意值。

### Inputs / Fields

- **Style:** 浅冷灰字段、6px 圆角、高对比占位文字。
- **Focus:** 边框切换为主色并出现克制焦点环。
- **Error / Disabled:** 使用语义色加明确文字，禁用态仍保留可读标签。

### Navigation

导航默认低强调；hover 使用次级表面，active 使用 Cobalt Soft 并提高文字权重。桌面稳定分栏，760px 以下收为抽屉；导航选中、悬停和键盘焦点必须可区分。

### Composer

Composer 是工作台首要操作面。白色表面、16px 圆角和轻结构阴影把它从内容层抬起；发送按钮是单一实色主操作，资料、模型和可见范围停留在较低层级。

## 6. Do's and Don'ts

### Do:

- **Do** 使用拍办蓝标记单屏唯一主操作，并保持高饱和视觉重量约 10% 以内。
- **Do** 使用姓名、身份标签、状态文字和图标共同说明 Agent / 真人与权限范围。
- **Do** 让大面积背景向品牌蓝紫轻微偏色，亮暗主题分别设计表面层级。
- **Do** 复用 Tutti 组件的键盘、弹层和控件行为，只在语义令牌与业务样式层定制。

### Don't:

- **Don't** 做成只有深灰层次、所有区域同权重的匿名 AI 控制台。
- **Don't** 使用霓虹渐变、装饰性玻璃拟态、满屏彩色按钮或夸张循环动效来制造“智能感”。
- **Don't** 复制 Kimi 的品牌资产、布局像素或文案。
- **Don't** 把每项信息都包成同尺寸卡片，或为卡片增加彩色侧条。
- **Don't** 让装饰压过权限、状态与真实正文，也不要只靠颜色表达状态。
