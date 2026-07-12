# FSAR GUI Redesign — Dynamic Glass

> **日期**: 2026-07-12
> **作者**: Claude (brainstorming + spec)
> **状态**: 待实施(由其他 AI 实施)
> **目标读者**: 实施该设计的 AI / 工程师

---

## 1. Overview

### 1.1 目标

把 FSAR 当前的"棱角分明 + 静态 + 单调"前端,全面重做为 **Dynamic Glass 风格** —— 黑白流动光晕 + 连续曲率 + spring 动效。

### 1.2 为什么需要这次重做

当前状态(`docs/superpowers/2026-07-03-p7-gui-design.md` 定义)的问题:

- 240px 死宽硬边侧栏,大量 `border-l-2 border-border-strong` 棱角
- 6px 圆角通配,无任何大圆角 / 药丸形
- Inter 字体(generic AI slop 标志)
- 6 个 token 调色板,无玻璃质感、无光晕
- framer-motion 装了几乎没用
- "No accent color anywhere"导致界面缺乏生命感
- "Hover: 120ms color/border swap" 平淡

### 1.3 范围

**全量翻盘 P7 阶段的设计哲学**:

| P7 原则(被推翻) | Dynamic Glass |
|---|---|
| No accent color anywhere | 严格黑白 + 流动光晕 |
| Border radius: 6px universal | 6 级连续曲率尺 + pill 9999px |
| Sidebar 240px fixed | 68px 悬浮胶囊 |
| Inter + Geist 字体 | 3 套字体可在 Settings 切换 |
| 120ms ease-out hover | 4 个 spring token 全场景弹性 |
| Hard 1px border active state | glow + layoutId 滑动 |

### 1.4 非目标

- ❌ **不重做 Onboarding Wizard** —— 单独后续 spec
- ❌ **不重做 Charts/Dashboards** (Insights / Usage) —— 后续 spec
- ❌ **不动后端** —— 纯前端改造
- ❌ **不动业务逻辑** —— 仅视觉/动效层

---

## 2. 美学方向:Dynamic Glass

### 2.1 命名

**Dynamic Glass**(不是 Liquid Glass —— 那是 Apple visionOS 的商标)。

### 2.2 灵感来源

- Apple visionOS 的 floating panels
- Linear / Vercel 的几何克制
- Arc / Notion AI 的暗色呼吸感
- 自创:**黑白流动光晕 + 极致留白 + 弹簧**

### 2.3 三条核心原则

1. **形状即胶囊** —— 按钮 = pill,卡片 = rounded-lg 以上,大面板 = rounded-xl
2. **表面即玻璃** —— 所有浮动元素用半透明 + backdrop-blur,看得见后面的内容
3. **生命即光晕** —— 唯一允许的彩色 = 黑白光晕,流动呼吸

### 2.4 风格定位

> **严格黑白底 + 黑白流动光晕 + 大量 spring 弹性 + 极致克制**
>
> 适合「伴侣」型产品的温度感,区别于 IDE 工具的冷峻。

---

## 3. 设计 Tokens

### 3.1 色彩系统(严格黑白,流动光晕)

#### Dark(默认在系统深色时)

```css
:root[data-theme="dark"] {
  --bg:           #0a0a0a;            /* 纯黑底 */
  --surface:      #141414;            /* 卡片底 */
  --surface-2:    #1c1c1c;            /* 悬浮态底 */

  --text:         #f5f5f5;            /* 永远不要 #fff */
  --text-muted:   #8a8a8a;
  --text-faint:   #5c5c5c;

  --border:       rgba(255, 255, 255, 0.08);
  --border-strong:rgba(255, 255, 255, 0.16);

  --glass:        rgba(255, 255, 255, 0.06);
  --glass-border: rgba(255, 255, 255, 0.10);

  --glow:         #ffffff;            /* 流动光主体 */
  --glow-soft:    rgba(255, 255, 255, 0.18);
  --glow-faint:   rgba(255, 255, 255, 0.06);
}
```

#### Light(默认在系统浅色时)

```css
:root[data-theme="light"] {
  --bg:           #ffffff;
  --surface:      #fafafa;
  --surface-2:    #f4f4f4;

  --text:         #0a0a0a;
  --text-muted:   #6b6b6b;
  --text-faint:   #a8a8a8;

  --border:       rgba(0, 0, 0, 0.08);
  --border-strong:rgba(0, 0, 0, 0.16);

  --glass:        rgba(0, 0, 0, 0.04);
  --glass-border: rgba(0, 0, 0, 0.10);

  --glow:         #0a0a0a;            /* 黑底时是黑色光 */
  --glow-soft:    rgba(0, 0, 0, 0.18);
  --glow-faint:   rgba(0, 0, 0, 0.04);
}
```

#### 语义色(只在状态徽章用,极小面积)

```css
--success: #34d399;  /* 仅 dark mode */
--warning: #fbbf24;
--danger:  #f87171;
--info:    #94a3b8;
```

状态徽章保持:**纯文字 + 2x2px 圆点**,不放大、不喧宾夺主。

### 3.2 字体系统(3 套实现,Settings 切换)

通过 `<html data-font-set="A|B|C">` 切换。Settings 加 3-按钮 toggle。

| Set | Display | Body | Mono | 气质 |
|---|---|---|---|---|
| **A** | Geist Sans 700 | **Geist Mono Variable** 400/500 | Geist Mono Variable 500 | 冷、技术、密 |
| **B** ⭐ 默认 | **Fraunces Variable** italic | **DM Sans Variable** 400/500 | JetBrains Mono Variable 400 | 温柔、故事感 |
| **C** | Geist Sans 600 | **Switzer Variable** 400/500 | Geist Mono Variable 400 | 克制、技术、中性 |

字体规则:

- Display → H1/H2、品牌名
- Body → 段落、按钮、表单
- Mono → 代码、token、模型名、文件路径、JSON

Tailwind 4 用 `--font-display` / `--font-sans` / `--font-mono` CSS 变量绑定。

### 3.3 几何系统(连续曲率 · 6 级)

```ts
borderRadius: {
  'xs':   '6px',     // 输入框、tag
  'sm':   '10px',    // 小按钮
  'md':   '14px',    // 标准卡
  'lg':   '20px',    // 大卡、面板
  'xl':   '28px',    // sheet/drawer
  '2xl':  '36px',    // 大对话框
  'pill': '9999px',  // 药丸 (按钮、输入框、tag)
}
```

**关键卡片(主面板、消息容器)用 Squircle(G2 连续曲率)**,不用普通圆角矩形。

```css
.squircle {
  /* 实现方式选一:
     1. SVG mask 的 superellipse
     2. 装 tailwindcss-squircle
     3. 手写 clip-path */
}
```

**Hairline** —— 1px,颜色用 `--border`(rgba),不用纯色 hairline。active 态用背景 + glow 取代 2px border。

### 3.4 动效系统(4 个 Spring)

```ts
// src/lib/motion/springs.ts
export const springs = {
  default: { type: "spring", stiffness: 260, damping: 26 },  // 进入/退出
  bouncy:  { type: "spring", stiffness: 380, damping: 18 },  // 按下/弹起
  smooth:  { type: "spring", stiffness: 200, damping: 24 },  // layoutId 滑动
  breath:  { type: "spring", stiffness: 80,  damping: 14 },  // 呼吸光晕(等价 3s ease-in-out loop)
} as const;
```

CSS fallback(非 framer 场景):

```css
--ease-standard:   cubic-bezier(0.32, 0.72, 0, 1);     /* Apple 默认 */
--ease-decelerate: cubic-bezier(0, 0, 0.2, 1);
--ease-accelerate: cubic-bezier(0.4, 0, 1, 1);
```

### 3.5 关键动画场景

| 场景 | 类型 | spring | 时长 |
|---|---|---|---|
| 页面入场(整页 stagger) | fade+y | default | — |
| Sidebar 图标 active | layoutId 滑动 | smooth | — |
| 按钮 hover | scale 1.06 | bouncy | — |
| 按钮 tap | scale 0.92 | bouncy | — |
| 消息气泡进入 | opacity+y+scale | default | — |
| 输入框 focus | border + glow ring | CSS | 300ms |
| Provider 下拉 | 高度+opacity 弹簧展开 | default | — |
| **主题切换** | **圆形 mask 揭示** | smooth | 480ms |
| 思考中三点 | 三点 staggered pulse | CSS | 1.2s loop |
| 角色卡 hover | scale + rotate 0.5° + glow | default | — |

**Reduced-motion & Motion=none 尊重**:所有动画在 `prefers-reduced-motion: reduce` 或 `[data-motion="none"]` 时降级为 0.01ms。

---

## 4. 组件原语

### 4.1 目录结构

```
src/components/ui/
├── primitives/
│   ├── Glass.tsx          # 玻璃面板
│   ├── Pill.tsx           # 药丸按钮
│   ├── Capsule.tsx        # 圆角容器(panel)
│   ├── BreathGlow.tsx     # 呼吸光晕
│   ├── Squircle.tsx       # G2 连续曲率
│   ├── IconButton.tsx     # 圆形按钮
│   ├── Tooltip.tsx        # 纯黑白 tooltip
│   ├── Toggle.tsx         # pill 开关
│   ├── Dropdown.tsx       # 玻璃下拉
│   ├── Sheet.tsx          # 滑出 sheet
│   ├── Tabs.tsx           # 下划线 layoutId 滑动
│   └── Input.tsx          # pill 输入框 + focus glow
├── motion/
│   ├── springs.ts         # 4 个 spring token
│   └── StaggerContainer.tsx
├── Avatar.tsx             # 修改(加 glow on hover)
├── BlackHole.tsx          # 改成动态光晕动画核心
└── Greeting.tsx           # 用 BreathGlow 包裹
```

### 4.2 必须新建的核心原语

#### `<Glass>` — 玻璃面板容器

```tsx
interface GlassProps {
  intensity?: 'low' | 'med' | 'high';  // 控制 blur 强度
  border?: boolean;                      // 默认 true
  children: React.ReactNode;
  className?: string;
}
```

- 内置 `backdrop-blur-2xl` + `--glass` 底色 + `--glass-border` 1px
- intensity: low=8px, med=16px, high=24px blur
- **Spring 进入**:`initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}` 用 default spring

#### `<Pill>` — 药丸按钮

```tsx
interface PillProps {
  variant?: 'primary' | 'ghost' | 'glass';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}
```

- 圆角 `9999px` (pill)
- **Primary**: `--text` 实色底 + `--bg` 文字 + glow shadow
- **Ghost**: 透明底 + hover 浮现 `--glass`
- **Glass**: 半透明玻璃底
- 内置 `whileHover scale 1.06` / `whileTap scale 0.92` (bouncy spring)
- `loading` 状态:文字替换为呼吸 3 点

#### `<Capsule>` — 圆角容器(Panel)

```tsx
interface CapsuleProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';  // 对应 rounded-xs/sm/md/lg
  interactive?: boolean;
  hoverable?: boolean;
}
```

- 圆角走 `md/lg/xl` (14/20/28px)
- `interactive`: 整块可点,hover 微 scale + glow 增量

#### `<BreathGlow>` — 呼吸光晕包装器

```tsx
interface BreathGlowProps {
  intensity?: 'low' | 'med' | 'high';
  active?: boolean;
  children: React.ReactNode;
}
```

- 内层放任意内容,外层覆一层 radial gradient + keyframes 呼吸
- `active` 控制是否在呼吸
- 用 `mask: radial-gradient` 实现"光从中心散出"
- 速度 `breath` spring 等价(3s loop,opacity 0.6↔1.0)

#### `<Squircle>` — G2 连续曲率容器

```tsx
interface SquircleProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  corner?: number;  // 0.10 平滑 / 0.18 标准 / 0.25 夸张
}
```

- 用 SVG mask 渲染超椭圆
- 用于主面板、消息容器、卡片 hero
- **跟普通 `rounded-lg` 视觉差距明显**(这是 Dynamic Glass 区别于普通 Apple 风的关键)

### 4.3 必须新建的表单原语

| 组件 | 要点 |
|---|---|
| `<Input>` | pill 圆角 + focus 时 `border-glow + 0 0 0 4px var(--glow-faint)` |
| `<IconButton>` | 圆形 28/36/44px,内置 hover/tap spring,icon size 14/16/18 |
| `<Tooltip>` | 黑/白底 + 白/黑字,8px 圆角,opacity fade,不投影 |
| `<Toggle>` | 36x20 pill 开关,thumb 16px 圆形,active 时 thumb 有 `--glow` |
| `<Dropdown>` | 基于 `<Glass>`,spring 高度展开(motion.div + layout) |
| `<Sheet>` | 右侧滑出 sheet,圆角左 28px,内嵌 `<Glass>` 风格 |
| `<Tabs>` | underline 用 `layoutId` 滑动,active 字色 + 微 glow |

### 4.4 必须修改的现有组件

| 组件 | 改动 |
|---|---|
| `<Avatar>` | 加 `glow on hover` 模式(`data-active` 时持续 glow) |
| `<Greeting>` | 整段改用 `<BreathGlow>` 包裹,字色用 display 字体 |
| `<BlackHole>` | 改成动态光晕动画核心(loading / processing 指示器) |

### 4.5 共享规则

- **所有** primitive 接受 `className` 转发(Tailwind merge)
- **所有** primitive 接受 `as` prop(默认 div/button)
- **所有** interactive 组件内置 spring motion(bouncy for buttons, default for cards)
- **所有** primitive 在 `data-motion="none"` 时降级为 CSS-only transitions

---

## 5. 布局:浮动胶囊组合

### 5.1 三元素组成

主界面 = **3 个浮动胶囊 + 1 个动态背景**,**没有任何死的网格分割**。

```
+----------------------------------------------------------+
| (动态背景: 3 个呼吸光晕缓慢飘动)                         |
|                                                          |
|  +-----+    +------------------------------------------+ |
|  | Side|    | Topbar (悬浮胶囊, 内含 Char | Mode | User) | |
|  | bar |    +------------------------------------------+ |
|  | 68  |                                                  |
|  | px  |    +------------------------------------------+ |
|  |     |    |                                          | |
|  | 浮  |    |     主内容区 (页面切换用 AnimatePresence) | |
|  | 动  |    |                                          | |
|  | 胶  |    |                                          | |
|  | 囊  |    |                                          | |
|  +-----+    +------------------------------------------+ |
+----------------------------------------------------------+
```

### 5.2 Sidebar(68px 悬浮胶囊)

```tsx
<motion.aside
  className="fixed left-3 top-3 bottom-3 z-40 w-[68px]
             glass rounded-pill
             flex flex-col items-center py-5 gap-1
             shadow-[0_8px_32px_rgba(0,0,0,0.24)]"
  initial={{ x: -32, opacity: 0 }}
  animate={{ x: 0, opacity: 1 }}
  transition={{ ...springs.smooth, delay: 0.05 }}
>
  {/* 顶部 logo: 小 36px 圆形,glow on hover */}
  {/* 8 个图标: 图标 only */}
  {/* 底部: 版本号 */}
</motion.aside>
```

每个图标:
- 圆形 40x40px,hover 浮现 `--glass` 底 + scale 1.08
- **active 态用 `layoutId="sidebar-active-pill"` 滑动** —— 切换页面时激活态不是硬切,是 spring 滑动
- 激活态同时有 `ring-1 ring-text/30` 和 `shadow-[0_0_24px_var(--glow-soft)]` 光晕

### 5.3 Topbar(48px 悬浮胶囊 + 中央切换器组)

```tsx
<motion.header
  className="fixed left-[88px] right-3 top-3 z-30 h-12
             glass rounded-pill
             flex items-center justify-between px-4"
>
  {/* 左侧: FSAR 品牌 */}
  <div>
    <span>FSAR</span> | <span>local-first agent</span>
  </div>

  {/* 中央: Character | AGENT/CHAT | User */}
  <CenterGroup />

  {/* 右侧: Theme + Provider */}
  <div>
    <ThemeToggle /> <ProviderSelector />
  </div>
</motion.header>
```

#### 中央 `<CenterGroup>` —— 三件套

```
+--------------------------------------------------+
| [Character ▾] | AGENT | CHAT | [User ▾]          |
+--------------------------------------------------+
```

- **CharacterSelector**(左) → pill 按钮,点击弹出 glass 下拉
- **AGENT/CHAT 切换**(中) → pill 容器内嵌 layoutId 滑动 thumb
- **UserSelector**(右) → pill 按钮,点击弹出 glass 下拉

整个三件套装在一个 `<Glass rounded-pill>` 容器内,三个 slot 之间用 4px gap 分隔。

### 5.4 主内容区

```tsx
<main className="absolute left-[88px] right-3 top-[72px] bottom-3 overflow-hidden">
  <AnimatePresence mode="wait">
    <motion.div
      key={location.pathname}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={springs.default}
      className="h-full w-full"
    >
      <Routes />
    </motion.div>
  </AnimatePresence>
</main>
```

**不要**全屏 flex 网格,要的是**绝对定位的浮动容器**,这样 3 个胶囊的圆角都能从背景里"浮"出来。

### 5.5 动态背景

```tsx
<div className="app-backdrop" aria-hidden="true">
  <div className="orb orb-1" />  {/* 左上,12s 漂移 */}
  <div className="orb orb-2" />  {/* 右下,18s 漂移 */}
  <div className="orb orb-3" />  {/* 中央,22s 漂移 */}
</div>
```

CSS:
```css
.app-backdrop {
  position: fixed; inset: 0;
  pointer-events: none; z-index: 0;
  background: var(--bg);
  overflow: hidden;
}
.app-backdrop .orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80-100px);
  will-change: transform;
  opacity: 0.45;  /* dark mode */
}
:root[data-theme="light"] .app-backdrop .orb {
  opacity: 0.25;
}
```

3 个 orb 的颜色用 `--glow-soft` 和 `--glow-faint`,不引入彩色。

---

## 6. 关键交互

### 6.1 Chat 发送框(悬浮胶囊,固定底部)

**当前问题**: `border-t border-border bg-surface` 死硬分割线 + 内嵌 `border border-border` 棱角按钮。

**改成**:

```
+------------------------------------------------------------+
|                                                            |
|              ⌘  Tell me about your day...   [Stop] [↵]     |  ← 悬浮胶囊
|                                                            |
+------------------------------------------------------------+
```

```tsx
<motion.div
  className="glass-strong rounded-pill pl-5 pr-2 py-2
             flex items-center gap-3
             glow-focus
             shadow-[0_12px_48px_rgba(0,0,0,0.32)]"
  initial={{ y: 24, opacity: 0 }}
  animate={{ y: 0, opacity: 1 }}
  transition={springs.smooth}
>
  <span>⌘</span>
  <input ... />
  <Pill size="sm" variant="ghost">Stop</Pill>
  <motion.button
    className="h-9 w-9 rounded-pill bg-text text-bg
               flex items-center justify-center
               shadow-[0_0_20px_var(--glow-soft)]"
    whileHover={{ scale: 1.08 }}
    whileTap={{ scale: 0.92 }}
    transition={springs.bouncy}
  >
    <Send size={14} strokeWidth={2} />
  </motion.button>
</motion.div>
```

**焦点光圈** —— `glow-focus` 工具类:

```css
.glow-focus:focus-within {
  border-color: var(--glow-soft);
  box-shadow: 0 0 0 4px var(--glow-faint);
}
```

### 6.2 AGENT/CHAT 切换 + Character/User 选择器

**全部迁移到 Topbar 中央**(详见 §5.3)。Chat.tsx 底部不再需要这三个组件。

### 6.3 History 面板

**当前问题**: `border-l border-border bg-surface` + `border-b border-border` + `border border-border-strong` 按钮。

**改成**:`glass rounded-2xl`,浮在 Chat 右侧,圆角大,内部按钮全 pill。

```tsx
<motion.aside
  className="glass rounded-2xl w-[280px] h-full
             flex flex-col overflow-hidden
             shadow-[0_8px_32px_rgba(0,0,0,0.20)]"
  initial={{ x: 16, opacity: 0 }}
  animate={{ x: 0, opacity: 1 }}
  transition={springs.smooth}
>
  <div className="flex items-center justify-between px-4 h-14">
    <span>History</span>
    <Pill size="sm" variant="primary" icon={<Plus />}>New</Pill>
    <IconButton onClick={onToggle}><PanelRightClose /></IconButton>
  </div>
  <div className="flex-1 overflow-y-auto px-2 pb-2">
    {sessions.map((s) => (
      <motion.div
        className="rounded-xl px-3 py-2.5 mb-1 cursor-pointer
                   hover:bg-glass
                   data-[active=true]:bg-glass
                   data-[active=true]:ring-1 data-[active=true]:ring-text/20
                   data-[active=true]:shadow-[0_0_18px_var(--glow-faint)]"
        whileHover={{ scale: 1.01 }}
      >
        <span>{s.title}</span>
        <div>{s.message_count} msg · {fmtRelative(s.updated_at)}</div>
        {/* hover 浮现 Pin/Pencil/Trash 三个 IconButton */}
      </motion.div>
    ))}
  </div>
</motion.aside>
```

### 6.4 消息气泡

**当前问题**: 段落文字 + `<hr>` 分割,无视觉层级。

**改成**:

- **User 消息**(右对齐): 实色底(`--text` 颜色 + `--bg` 文字)pill,右下角略小(像 iMessage)
- **Assistant 消息**(左对齐): glass 背景 pill,左下角略小
- 消息之间用 16-24px gap,不画 `<hr>`
- 气泡进入用 `opacity+y+scale` spring

```tsx
<div className="glass rounded-2xl rounded-bl-md px-4 py-2.5">
  <span>Hi, I'm here. What's on your mind today?</span>
</div>

<div className="bg-text text-bg rounded-2xl rounded-br-md
                shadow-[0_0_20px_var(--glow-faint)]">
  <span>Tell me about your day.</span>
</div>
```

### 6.5 主题切换(圆形 mask 揭示)

**创新点** —— 切换主题时,屏幕从点击位置扩散圆形揭示新主题:

```tsx
function handleThemeSwitch(event: MouseEvent) {
  const x = event.clientX, y = event.clientY;
  const endRadius = Math.hypot(
    Math.max(x, innerWidth - x),
    Math.max(y, innerHeight - y)
  );
  document.documentElement.style.setProperty('--clip-x', `${x}px`);
  document.documentElement.style.setProperty('--clip-y', `${y}px`);
  document.documentElement.style.setProperty('--clip-size', `${endRadius}px`);
  document.documentElement.classList.add('theme-transitioning');
  // 用 View Transitions API:
  // document.startViewTransition(() => themeChange());
}

document.startViewTransition(() => {
  // apply new theme
});
```

CSS:
```css
::view-transition-group(root) {
  clip-path: circle(var(--clip-size) at var(--clip-x) var(--clip-y));
}
```

这是 Apple 风格主题切换的招牌动作。

### 6.6 思考中指示器

3 个圆点 staggered pulse,每点延迟 0.2s,1.2s loop:

```css
@keyframes pulse {
  0%, 100% { transform: scale(0.8); opacity: 0.5; }
  50% { transform: scale(1.2); opacity: 1; }
}
.dot { animation: pulse 1.2s ease-in-out infinite; }
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
```

---

## 7. Settings 新增

### 7.1 字体集切换器

在 Style tab 加 3-按钮 toggle:

```tsx
<div className="flex items-center gap-2">
  {(['A', 'B', 'C'] as const).map(set => (
    <Pill
      variant={currentSet === set ? 'primary' : 'ghost'}
      onClick={() => setFontSet(set)}
    >
      Set {set}
    </Pill>
  ))}
</div>
```

切换时 `<html data-font-set="...">` 立即更新,CSS 变量跟着变。

### 7.2 现有 Style 改造

Style tab 整体改用 Dynamic Glass 风格:玻璃容器 + pill 按钮 + spring 动效。

---

## 8. 实施迁移策略

### Phase 1:基础设施(1 天)

1. 装字体包 (`@fontsource-variable/dm-sans`、`fraunces`、`jetbrains-mono`)
2. 重写 `globals.css` 完整 token 系统(§3)
3. 重写 `tailwind.config.ts` 字体 + 圆角 + keyframes
4. 创建 `src/lib/motion/springs.ts`

### Phase 2:原语层(1-2 天)

按 §4 顺序创建所有原语组件。每个原语写完后写一个 story 或 demo 页面验证视觉。

### Phase 3:布局(1 天)

1. 改 `Sidebar.tsx` → 68px 浮动胶囊(§5.2)
2. 改 `Topbar.tsx` → 48px 浮动胶囊 + 中央三件套(§5.3)
3. 改 `app.tsx` → 浮动布局 + AnimatePresence 页面切换(§5.4)
4. 改 `globals.css` 加 `.app-backdrop` + `.orb`(§5.5)

### Phase 4:Chat 关键交互(1-2 天)

1. 重写 Chat 发送框(§6.1)
2. 迁移 Character / User Selector 到 Topbar(§6.2)
3. 重写 HistoryPanel(§6.3)
4. 重写消息气泡(§6.4)

### Phase 5:Polish(1 天)

1. 主题切换圆形 mask(§6.5)
2. 思考中三点 pulse(§6.6)
3. 入场 stagger 动画
4. Settings 字体切换器(§7)
5. 性能检查(backdrop-blur 在低端设备会卡)

---

## 9. 验收清单

实施完成后逐项打勾:

- [ ] **没有任何 `rounded`(4px) 元素** —— 至少 md(14px)或 pill(9999px)
- [ ] **没有任何 `border-2 border-border-strong` active 态** —— 用 glow 取代
- [ ] **没有任何纯黑/纯白底** —— dark=#0a0a0a, light=#ffffff 已是底线,正文 bg 至少 surface 一档
- [ ] **没有任何 Inter 字体显示** —— Set B 默认完全不出现 Inter
- [ ] **3 个浮动胶囊都在背景上"浮"** —— 有明显阴影 + 玻璃模糊
- [ ] **侧栏切换有 layoutId 滑动** —— 不是硬切
- [ ] **主题切换有圆形 mask 揭示**
- [ ] **所有按钮 hover/tap 有 spring 弹性**
- [ ] **输入框 focus 有光晕**
- [ ] **Settings 字体切换实时生效**
- [ ] **`prefers-reduced-motion: reduce` 时所有动效降级**

---

## 10. 不在本次范围(后续 spec)

- Onboarding Wizard 全部重做(已有 PL2.1 spec,本次不动)
- Library / Memory / Reflection / Insights / Usage 页面内部 UI 改造(本次只换 shell + token,内部按钮和卡片沿用 Dynamic Glass 通用规则)
- Tauri native 主题适配(等前端稳了再处理)
- 移动端布局(完全未考虑)

---

## 11. 风险 & 注意

| 风险 | 应对 |
|---|---|
| `backdrop-blur` 性能差 | 在低配设备降级为普通模糊或纯色 |
| `framer-motion` bundle 大(90KB+) | 用 dynamic import / 手动 spring 减少初始加载 |
| 用户已经习惯 P7 硬边设计 | 接受过渡期反馈,Settings 加"返回 P7"逃生通道(可选) |
| Squircle 在 Firefox 支持差 | 用 SVG mask fallback |
| View Transitions API 在 Safari < 18 不支持 | 降级为 opacity fade |

---

## 12. 参考资源

- `docs/superpowers/2026-07-03-p7-gui-design.md` —— 被推翻的 P7 设计
- `docs/superpowers/specs/2026-07-08-chat-session-management-design.md` —— 现有聊天设计
- `docs/superpowers/specs/2026-07-09-pl2-0-persona-foundation-design.md`
- `docs/superpowers/specs/2026-07-10-pl2-1-onboarding-wizard-design.md`
- `frontend/src/components/ui/` —— 现有 UI 组件目录
- `frontend/src/stores/ui.ts` —— 现有 Theme/Density/Motion store

---

**Spec 状态:完成,等用户审阅确认**