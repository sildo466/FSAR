# 皮肤系统 `data/skins/`

> 语言：中文 | [English](skin.en.md) · 返回 [模块索引](README.md)

FSAR 的皮肤（skin）是一个**纯数据**文件：一份 `skin.json` 描述整站的配色、聊天壁纸、组件（按钮/输入框/开关/标签/卡片）颜色与纹理。皮肤不写任何代码逻辑——由前端管线把 `skin.json` 解析后写成 CSS 变量，全站即时响应。

皮肤是 FSAR 的**卖点**：让聊天伴侣从"对话工具"变成"有视觉身份的东西"。你可以在聊天页面铺一张壁纸，把所有按钮染成你的颜色，给输入框加纹理，甚至把一个主题的基础刷上你自己的调色板。

## 皮肤长什么样

```json
{
  "id": "warm",
  "name": "暖阳",
  "version": 1,
  "base": "light",
  "palette": {
    "bg": "#faf8f5",
    "text": "#2a2a2a",
    "accent": "#d4a04a"
  },
  "background": {
    "chatImage": "/skin-assets/warm/bg.png",
    "chatOverlay": 0.85
  },
  "elements": {
    "button": { "bg": "#d4a04a", "text": "#ffffff" },
    "card":   { "bg": "#ffffff", "image": "/skin-assets/warm/tex.svg", "imageOpacity": 0.4 }
  },
  "pattern": {
    "image": "/skin-assets/warm/tex-pattern.svg",
    "opacity": 0.5
  }
}
```

## 文件放哪里

每个皮肤一个目录，内含 `skin.json`（必须，文件名与 `id` 一致）：

```
data/skins/<id>/skin.json   # 内置预设（随项目分发）
~/.fsar/data/skins/<id>/skin.json   # 个人皮肤（推荐，不进 git / 不进远程）
```

- 个人皮肤放 `~/.fsar/data/skins/` 最干净——只在你本机，绝不会被提交到远程仓库。
- 内置预设放仓库 `data/skins/`，会随代码一起分发。
- 皮肤资产（壁纸、纹理图）放同目录的 `assets/`，前端通过 `/skin-assets/<id>/<file>` 访问。

## 最简皮肤

只写你想改的部分，其余自动回落 `base` 对应的默认配色（`light` 或 `dark`）：

```json
{
  "id": "my-skin",
  "name": "我的皮肤",
  "base": "light",
  "palette": {
    "accent": "#c0392b",
    "text": "#222222"
  }
}
```

把这份文件存成 `data/skins/my-skin/skin.json`，刷新后 Settings → 外观 → 皮肤 → 我的皮肤，你就会看到：强调色变深红、正文变深灰，其它一切保持不变。

## palette — 全局配色（17 个键）

`palette` 控制全站的基础色。以下键都可以覆盖（键名 = 去掉 `--` 前缀的 CSS 变量名）：

| 键 | CSS 变量 | 作用 |
|----|---------|------|
| `bg` | `--bg` | 页面背景（chat 场景下是壁纸底色） |
| `surface` | `--surface` | 卡片/面板底色 |
| `surface2` | `--surface-2` | 次级面板（更实的表面） |
| `text` | `--text` | 正文颜色 |
| `textMuted` | `--text-muted` | 次要文字 |
| `textFaint` | `--text-faint` | 弱化文字（占位符、标签） |
| `border` | `--border` | 常规边框 |
| `borderStrong` | `--border-strong` | 强调边框 |
| `glass` | `--glass` | 玻璃面板（毛玻璃效果） |
| `glassStrong` | `--glass-strong` | 强玻璃（弹窗、模态） |
| `glassBorder` | `--glass-border` | 玻璃边框 |
| `glowSoft` | `--glow-soft` | 柔和辉光 |
| `glowFaint` | `--glow-faint` | 淡辉光 |
| `success` | `--success` | 成功状态 |
| `warning` | `--warning` | 警告状态 |
| `danger` | `--danger` | 错误状态 |
| `accent` | `--accent` | 强调色（主按钮、开关、选中等） |

颜色可用 hex（`#rrggbb` / `#rgb`）或 `rgba(r,g,b,a)`。

## elements — 逐元素自定义

`elements` 让某一类组件**独立于全局配色**。每个元素有各自的键白名单，只认列出的字段：

| 元素 | 字段 | 作用 | 默认（= palette） |
|------|------|------|------|
| `input` | `bg` `border` `text` | 输入框/下拉/多行 | glass / glassBorder / text |
| `button` | `bg` `text` `hover` `image` `imageOpacity` | 主按钮/实底按钮 | accent / bg / accent |
| `switch` | `on` `off` `thumb` | 开关 | accent / borderStrong / surface2 |
| `chip` | `bg` `border` | 标签 pill | glowFaint / border |
| `card` | `bg` `border` `image` `imageOpacity` | 卡片/玻璃面板 | glass / glassBorder |

`image`（贴图）可以把一张图作为组件的纹理铺在底色上，`imageOpacity`（0–1）调透明度；`image` 留空即无纹理。

> 注意：`input`/`button` 等迁移了全站对应组件（含内联控件），改一个元素会统一影响所有实例——这正是"逐元素"的意义。

## background — 聊天壁纸

```json
"background": {
  "chatImage": "/skin-assets/my-skin/bg.png",
  "chatOverlay": 0.85
}
```

- `chatImage`：聊天页面壁纸。同源路径（`/skin-assets/<id>/<file>`）或完整 URL 均可；留空即无壁纸。
- `chatOverlay`（0–1，缺省 `0.85`）：壁纸上覆盖层的不透明度。**覆盖层颜色 = 该皮肤解析后的 `bg` 色**，所以无论壁纸多花哨，文字对比度始终有保障。想壁纸更透、更醒目就调低；文字变糊就调高。

## pattern — 全局纹理

```json
"pattern": {
  "image": "/skin-assets/my-skin/tex.svg",
  "opacity": 0.5
}
```

`pattern` 在全站铺一层很淡的 **background-image**（`body::after`，`z-index:-1` 在最底、`pointer-events:none`），透过玻璃面板若隐若现。`opacity` 0–1 控制浓淡。

- **提示**：`pattern` 一般用 `repeat` 平铺的小纹理（如 SVG 花纹），而不是一整张大图。
- 因为 chat 页面有自己的壁纸（`background.chatImage`），全局纹理在 chat 区通常不显示——这是预期行为，去设置/调度器那些页面看效果。

## 贴图资产

- 壁纸/纹理图放进 `assets/`，用 `/skin-assets/<id>/<file>` 引用（后端只读路由，带路径穿越防护）。
- 小纹理强烈建议手写 **SVG**（几 KB、可平铺、无额外体积）——比如一个 40×40 的格纹、菱形、圆环图案，比大图更适合当组件纹理/全局纹理。
- 资产缺失时优雅回落：壁纸回纯色、纹理回无纹理，不红屏。

## 分层规则（重要）

最终每个 token 的值按这个优先级：

```
elements 覆盖  >  palette 覆盖  >  该 base 的内置默认
```

- 你没写 `elements.button.bg` → 用 `palette.accent`
- 你没写 `palette.accent` → 用 `base: "light"`（或 `"dark"`）的内置默认
- 所以皮肤可以只写一个 `accent`，其余全自动

## 三个内置示例对照

| id | name | base | 特征 |
|----|------|------|------|
| warm | 暖阳 | light | 暖米底 `#faf8f5`、金 accent `#d4a04a` |
| night | 暗紫 | dark | 暗紫底 `#14121a`、紫 accent `#a78bfa` |
| minimal | 极简 | light | 高灰阶、弱辉光、几乎无纹理 |

把它们当模板：复制一份、改 `id/name` 和几个色值，就是你的皮肤。

## 已知边界

- 圆角/阴影（`radius`/`shadow`）暂不随皮肤变化，由组件自身的 Tailwind 类决定——后续版本可能开放。
- 状态色 chip（success/warning/danger 着色的）保持语义 token，不并入 `chip`。
- 皮肤保存/编辑器/市场尚未实现：当前皮肤 = 手写 JSON 文件。需要图形化编辑 → 后续版本（编辑器路线）。

## 快速上手

1. `mkdir -p ~/.fsar/data/skins/my-skin && cp data/skins/minimal/skin.json ~/.fsar/data/skins/my-skin/skin.json`
2. 改 `id` 为 `my-skin`、改 `name`、调几个 `palette` / `elements` 色
3. （可选）放张图到 `assets/`，加 `background.chatImage` 指向它
4. 刷新浏览器 → Settings → 外观 → 皮肤 → 选它

改 `skin.json` 随时生效（每次切到该皮肤重新应用），不需要重启后端。CSS 变量写死在运行时，`npm run build` 只影响默认观感，不影响皮肤数据。
