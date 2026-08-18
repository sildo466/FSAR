# Skin system `data/skins/`

> Language: English | [中文](skin.md) · back to [module index](README.md)

An FSAR skin is a **pure data** file: one `skin.json` describes the site-wide palette, the chat wallpaper, and per-component (button / input / switch / chip / card) colors and textures. Skins carry no logic — the frontend pipeline parses `skin.json` into CSS variables and the whole app responds instantly.

Skins are one of FSAR's headline features: they turn the chat companion from a "dialog tool" into something with a **visual identity**. Put a wallpaper on the chat page, dye every button in your colour, add a texture to the input field, or base a theme on your own palette.

## What a skin looks like

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

## Where to put it

One directory per skin, containing `skin.json` (required, filename must match `id`):

```
data/skins/<id>/skin.json              # built-in presets (shipped with the project)
~/.fsar/data/skins/<id>/skin.json      # personal skins (recommended — never committed/pushed)
```

- Put personal skins under `~/.fsar/data/skins/` — local only, never in a remote repo.
- Put built-in presets under the repo's `data/skins/` so they ship with the code.
- Skin assets (wallpaper, textures) go in `assets/` beside `skin.json`, served at `/skin-assets/<id>/<file>`.

## Minimal skin

Write only what you want to change; everything else falls back to the `base` defaults (`light` or `dark`):

```json
{
  "id": "my-skin",
  "name": "My Skin",
  "base": "light",
  "palette": {
    "accent": "#c0392b",
    "text": "#222222"
  }
}
```

Save it as `data/skins/my-skin/skin.json`, refresh, pick it in Settings → Appearance → Skin: the accent becomes deep red, body text goes dark grey, everything else stays the same.

## palette — global colours (17 keys)

`palette` drives the base colours of the whole app:

| key | CSS var | role |
|-----|---------|------|
| `bg` | `--bg` | page background (base colour under the chat wallpaper) |
| `surface` | `--surface` | card / panel background |
| `surface2` | `--surface-2` | secondary panel (more opaque) |
| `text` | `--text` | body text |
| `textMuted` | `--text-muted` | secondary text |
| `textFaint` | `--text-faint` | faint text (placeholders, captions) |
| `border` | `--border` | normal border |
| `borderStrong` | `--border-strong` | emphasis border |
| `glass` | `--glass` | glass panel (frosted glass) |
| `glassStrong` | `--glass-strong` | strong glass (modals, popovers) |
| `glassBorder` | `--glass-border` | glass border |
| `glowSoft` | `--glow-soft` | soft glow |
| `glowFaint` | `--glow-faint` | faint glow |
| `success` | `--success` | success state |
| `warning` | `--warning` | warning state |
| `danger` | `--danger` | error state |
| `accent` | `--accent` | accent (primary buttons, switches, selection) |

Hex (`#rrggbb` / `#rgb`) or `rgba(r,g,b,a)` are both fine.

## elements — per-component customisation

`elements` makes one component class independent of the global palette. Each element has an allow-listed field set:

| element | fields | role | default (= palette) |
|---------|--------|------|------|
| `input` | `bg` `border` `text` | inputs / selects / textareas | glass / glassBorder / text |
| `button` | `bg` `text` `hover` `image` `imageOpacity` | primary / solid buttons | accent / bg / accent |
| `switch` | `on` `off` `thumb` | toggle switch | accent / borderStrong / surface2 |
| `chip` | `bg` `border` | tag pill | glowFaint / border |
| `card` | `bg` `border` `image` `imageOpacity` | cards / glass panels | glass / glassBorder |

`image` textures a component (laid over its `bg`), `imageOpacity` (0–1) controls its strength; leave `image` empty for no texture.

> `input` / `button` migrations cover all matching components across the app (including inline controls) — changing one element restyles every instance. That's the point of per-element theming.

## background — chat wallpaper

```json
"background": {
  "chatImage": "/skin-assets/my-skin/bg.png",
  "chatOverlay": 0.85
}
```

- `chatImage`: chat wallpaper. A same-origin path (`/skin-assets/<id>/<file>`) or a full URL; empty disables the wallpaper.
- `chatOverlay` (0–1, default `0.85`): opacity of the overlay on the wallpaper. The overlay colour equals this skin's resolved `bg`, so text stays readable no matter how busy the wallpaper is. Lower it for a more transparent, vivid backdrop; raise it if text gets hard to read.

## pattern — global texture

```json
"pattern": {
  "image": "/skin-assets/my-skin/tex.svg",
  "opacity": 0.5
}
```

`pattern` lays a very light **background-image** over the whole site (`body::after`, `z-index:-1`, `pointer-events:none`) that faintly shows through glass panels. `opacity` (0–1) sets the strength.

- Tip: use a small tileable texture (an SVG pattern), not a large photo.
- Since the chat page has its own wallpaper, the global texture usually doesn't show there — that's expected. Check it on Settings / Scheduler.

## Texture assets

- Wallpapers / textures go in `assets/`, referenced as `/skin-assets/<id>/<file>` (a read-only route with path-traversal protection).
- For small textures prefer hand-written **SVG** (a few KB, tileable, zero overhead) — a 40×40 chevron, diamond or ring pattern reads better as a component / global texture than a big image.
- Missing assets degrade gracefully: wallpaper falls back to a solid colour, texture to nothing — no crash.

## Precedence (important)

Each token's final value resolves in this order:

```
elements override  >  palette override  >  built-in default for this base
```

- no `elements.button.bg` → uses `palette.accent`
- no `palette.accent` → uses the built-in default for `base: "light"` (or `"dark"`)
- so a skin can set just `accent` and everything else follows

## The three built-in skins

| id | name | base | character |
|----|------|------|-----------|
| warm | 暖阳 | light | warm beige `#faf8f5`, gold accent `#d4a04a` |
| night | 暗紫 | dark | dark purple `#14121a`, violet accent `#a78bfa` |
| minimal | 极简 | light | high grey scale, weak glow, nearly texture-less |

Treat them as templates: copy one, change `id`/`name` and a few values, and it's your skin.

## Known boundaries

- Corner radii / shadows (`radius`/`shadow`) are not skin-driven yet — components keep their own Tailwind classes. A later release may open them.
- State chips (success/warning/danger-coloured) keep their semantic tokens and are not merged into `chip`.
- Skin saving / editor / marketplace are not implemented yet: a skin is a hand-written JSON file. Graphical editing is on a later (editor) track.

## Quick start

1. `mkdir -p ~/.fsar/data/skins/my-skin && cp data/skins/minimal/skin.json ~/.fsar/data/skins/my-skin/skin.json`
2. Change `id` to `my-skin`, change `name`, tweak a few `palette` / `elements` values
3. (Optional) drop an image into `assets/`, point `background.chatImage` at it
4. Refresh the browser → Settings → Appearance → Skin → pick it

Editing `skin.json` takes effect immediately (reapplied each time you select the skin); no backend restart needed. CSS variables are resolved at runtime — `npm run build` only affects the default look, not skin data.
