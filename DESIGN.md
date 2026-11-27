# KrlzCut — Design System Specification (`DESIGN.md`)

> Adapted from `runwayml` (`VoltAgent/awesome-design-md`) and calibrated for a dark-mode local desktop AI video-editing studio (`KrlzCut 2.0`), strictly enforcing `design-taste-frontend` anti-slop guardrails.

---

## 1. Visual Theme & Atmosphere

- **Philosophy**: Broadcast-grade dark nonlinear video-editing (NLE) restraint. The interface behaves like a calibrated grading monitor: 92–95% neutral obsidian surfaces, exact 1px structural hairlines, and crisp paper-white primary actions. Colour belongs strictly to the user's video frames, clip thumbnails, subtitle preview, and functional telemetry—never to decorative neon glows or gradient chrome.
- **Surface Polarity**: Dark-first monochrome studio (`#0A0A0B` canvas, `#111113` panels, `#18181B` interactive controls).
- **Information Density**: Medium-high studio precision. Generous 24px–32px structural margins between workgroups paired with compact, scannable inspector rows (`36px–40px` control heights) and `tabular-nums` on every timecode, percentage, and byte readout.
- **Signature Characteristics**:
  - Zero ambient neon blobs, zero drop-shadow glow halos, and zero violet/purple/lavender anywhere in the default interface.
  - Pure tonal surface stepping (`#0A0A0B` → `#111113` → `#18181B` → `#222226`) with 1px hairlines (`rgba(255, 255, 255, 0.08)`).
  - Solid Paper-White (`#FAFAFA`) primary action buttons with `#09090B` ink—one unmistakable primary action per screen.
  - Crisp `1.75px`-stroke monochrome SVG iconography throughout (zero emojis in UI chrome).
  - Direct, plain studio copy: headings name tools/objects, buttons are verb + object.

---

## 2. Color Palette & Roles

| Role | Token | Value | Usage |
|---|---|---|---|
| **Page Canvas** | `--bg` | `#0A0A0B` | Main application background; never pure `#000000` |
| **Sidebar / Shell** | `--bg-sidebar` | `#0E0E10` | Persistent left navigation rail, 1px right hairline |
| **Elevated Surface** | `--surface` | `#111113` | Studio cards, inspector cards, modal panels |
| **Control Surface** | `--surface-2` | `#18181B` | Inputs, selects, secondary buttons, inactive chips |
| **Control Hover** | `--surface-hover` | `#222226` | Hover state for controls, list rows, and chips |
| **Selected Surface** | `--surface-active` | `#27272A` | Selected nav item, selected preset/card infill |
| **Media Well** | `--media-bg` | `#050506` | Video viewport, filmstrip well, thumbnail fallback |
| **Primary Text** | `--text` | `#F4F4F5` | Headings, primary labels, active values (>16:1 contrast on `#0A0A0B`) |
| **Secondary Text** | `--muted` | `#A1A1AA` | Descriptions, meta rows, inactive nav labels (>7.2:1 contrast on `#0A0A0B`) |
| **Tertiary Text** | `--muted-2` | `#787882` | Hints, timestamps, subtle section captions (>=4.6:1 contrast on `#0A0A0B`) |
| **Hairline Border** | `--border` | `rgba(255, 255, 255, 0.08)` | Default 1px structural divider on cards, sidebar, inputs |
| **Strong Border** | `--border-strong` | `rgba(255, 255, 255, 0.16)` | Hover borders, active control outlines |
| **Selected Border** | `--border-active` | `rgba(255, 255, 255, 0.32)` | Selected cards and active studio modes |
| **Primary Action Fill** | `--action` | `#FAFAFA` | Solid primary CTA background (default Obsidian theme) |
| **Primary Action Ink** | `--action-ink` | `#09090B` | Text/icon on `--action` (>18:1 contrast) |
| **Primary Action Hover** | `--action-hover` | `#FFFFFF` | Hover fill for primary CTA |
| **Signal Telemetry Accent** | `--signal` | `#0EA5E9` | Playhead trim highlight, active range accent, progress ring A (non-violet) |
| **Signal Secondary** | `--signal-2` | `#F59E0B` | GPU telemetry ring, warning highlight |
| **Focus Ring** | `--focus-ring` | `#FAFAFA` | 2px keyboard `:focus-visible` outline (`outline-offset: 2px`) |
| **Semantic Success** | `--success` | `#22C55E` | Ready status dot/badge, engine OK, RAM ring |
| **Semantic Success Fill** | `--success-bg` | `rgba(34, 197, 94, 0.12)` | Status pill background (paired with `#4ADE80` text) |
| **Semantic Warning** | `--warn` | `#F59E0B` | Pending/warning dot, amber theme primary |
| **Semantic Danger** | `--danger` | `#EF4444` | Error status, destructive button border/text |
| **Semantic Danger Fill** | `--danger-bg` | `rgba(239, 68, 68, 0.12)` | Destructive hover/error box fill (paired with `#FCA5A5` text) |

### Approved Optional Studio Themes (Settings Switcher — Zero Violet)
- `obsidian` (default): `--action: #FAFAFA`, `--action-ink: #09090B`, `--signal: #0EA5E9`, `--signal-2: #F59E0B`
- `amber`: `--action: #F59E0B`, `--action-ink: #09090B`, `--signal: #F59E0B`, `--signal-2: #EA580C`
- `emerald`: `--action: #10B981`, `--action-ink: #05140E`, `--signal: #10B981`, `--signal-2: #06B6D4`
- `cobalt`: `--action: #3B82F6`, `--action-ink: #FFFFFF`, `--signal: #3B82F6`, `--signal-2: #0EA5E9`
- `crimson`: `--action: #EF4444`, `--action-ink: #FFFFFF`, `--signal: #EF4444`, `--signal-2: #F97316`
- `custom`: User-picked `--theme-a` and `--theme-b` applied cleanly via `color-mix(in oklab, ...)` (never `oklch` with neutrals).

---

## 3. Typography Rules

### Font Families
- **UI & Display Sans**: `"Inter", -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif`
- **Monospace / Telemetry**: `"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` (timecodes, hex codes, diagnostics logs)

### Allowed Numeric Weights
- `400` (Regular) — body copy, descriptions, inputs
- `500` (Medium) — navigation items, chips, form labels, secondary buttons
- `600` (SemiBold) — card titles, primary buttons, section headings, telemetry figures

### Type Scale

| Role | Token | Size | Weight | Line Height | Letter Spacing | Features |
|---|---|---|---|---|---|---|
| **Page Title (H1)** | `--t-h1` | `26px` | `600` | `1.15` (`30px`) | `-0.03em` | Sentence case |
| **Section Heading (H2)** | `--t-h2` | `17px` | `600` | `1.25` (`21px`) | `-0.02em` | Sentence case |
| **Card Title (H3)** | `--t-h3` | `15px` | `600` | `1.3` (`20px`) | `-0.015em` | Sentence case |
| **Inspector Heading (H4)** | `--t-h4` | `13px` | `600` | `1.3` (`17px`) | `-0.01em` | Sentence case |
| **Body** | `--t-body` | `14px` | `400` | `1.5` (`21px`) | `-0.005em` | Max line width 62ch |
| **Control / Button** | `--t-btn` | `13.5px` | `500` | `1.0` (`14px`) | `-0.01em` | No uppercase |
| **Label / Meta** | `--t-meta` | `13px` | `400` | `1.4` (`18px`) | `0` | `font-variant-numeric: tabular-nums` |
| **Micro Tag / Eyebrow** | `--t-micro` | `12px` | `500` | `1.25` (`15px`) | `0.02em` | `tabular-nums` |
| **Telemetry Value** | `--t-stat` | `16px` | `600` | `1.1` (`18px`) | `-0.02em` | `tabular-nums` |

---

## 4. Component Stylings

### Buttons (Strict 4-Variant System)
All buttons share `border-radius: 8px`, `font-size: 13.5px`, `font-weight: 500`, `transition: background-color 150ms ease, border-color 150ms ease, transform 120ms ease`.

1. **Primary (`.btn-primary`, `.btn-launch-big`)**:
   - `default`: `height: 40px` (`44px` for main launch CTA), `padding: 0 16px`, `background: var(--action)`, `color: var(--action-ink)`, `border: 1px solid transparent`, `box-shadow: none`.
   - `hover`: `background: var(--action-hover)`, `transform: translateY(-1px)`.
   - `active`: `transform: scale(0.985)`.
   - `focus-visible`: `outline: 2px solid var(--focus-ring); outline-offset: 2px`.
   - `disabled`: `opacity: 0.45; cursor: not-allowed; transform: none`.
2. **Secondary / Ghost (`.btn-ghost`)**:
   - `default`: `height: 36px` (`40px` in forms), `padding: 0 14px`, `background: var(--surface-2)`, `color: var(--text)`, `border: 1px solid var(--border)`.
   - `hover`: `background: var(--surface-hover)`, `border-color: var(--border-strong)`.
   - `active`: `transform: scale(0.985)`.
   - `disabled`: `opacity: 0.45; cursor: not-allowed`.
3. **Destructive (`.btn-ghost.danger`)**:
   - `default`: `background: transparent`, `color: #F87171`, `border: 1px solid rgba(239, 68, 68, 0.28)`.
   - `hover`: `background: var(--danger-bg)`, `border-color: rgba(239, 68, 68, 0.50)`.
4. **Segmented Chips & Pills (`.mini-chip`, `.filter-pill`, `.preset-pill`, `.mega-pill`)**:
   - `default`: `height: 32px`, `padding: 0 12px`, `border-radius: 6px`, `background: var(--surface-2)`, `border: 1px solid var(--border)`, `color: var(--muted)`, `font-size: 13px`, `font-weight: 500`.
   - `hover`: `background: var(--surface-hover)`, `color: var(--text)`, `border-color: var(--border-strong)`.
   - `active / selected`: `background: var(--action)`, `color: var(--action-ink)`, `border-color: var(--action)`.

### Cards & Panels (`.studio-card`, `.mode-launch-card`, `.proj-card`, `.insp-card`)
- `background: var(--surface)`, `border: 1px solid var(--border)`, `border-radius: 12px`, `padding: 20px` (`16px` inside inspector), `box-shadow: none`.
- Interactive cards hover: `border-color: var(--border-strong)`, `transform: translateY(-2px)` (`180ms cubic-bezier(0.2, 0.8, 0.2, 1)`).
- Thumbnail images inside cards zoom `transform: scale(1.025)` on card hover inside `overflow: hidden`.
- **Two boxes deep maximum**: Internal groupings inside cards use `border-top: 1px solid var(--border)` rules rather than nested bordered boxes.

### Inputs, Selects & Textareas
- `height: 38px` (`42px` primary URL input), `padding: 0 12px`, `border-radius: 6px`, `background: var(--media-bg)`, `border: 1px solid var(--border)`, `color: var(--text)`, `font-size: 13.5px`.
- `hover`: `border-color: var(--border-strong)`.
- `focus-visible`: `border-color: var(--action)`, `outline: 2px solid color-mix(in oklab, var(--action) 25%, transparent)`.

### Sidebar Navigation (`.sidebar`, `.nav-item`)
- Width: `248px`, `background: var(--bg-sidebar)`, `border-right: 1px solid var(--border)`, `padding: 16px 12px`.
- `.nav-item`: `height: 38px`, `padding: 0 12px`, `border-radius: 8px`, `color: var(--muted)`, `font-size: 13.5px`, `font-weight: 500`, `gap: 10px`.
- `.nav-item.active`: `background: var(--surface-active)`, `color: var(--text)`, `border: 1px solid var(--border-strong)`.

### Badges & Status Pills (`.status-pill`)
- `height: 24px`, `padding: 0 9px`, `border-radius: 4px`, `font-size: 12px`, `font-weight: 500`, `border: 1px solid var(--border)`, `background: var(--surface-2)`.
- Status is always conveyed via **text + dot/icon + color** (never color alone).

### Modals & Mega Clip Editor (`.modal`, `.modal-panel`, `.mega-editor`)
- Backdrop: `rgba(5, 5, 6, 0.82)` with `backdrop-filter: blur(8px)`.
- Panel: `background: var(--surface)`, `border: 1px solid var(--border-strong)`, `border-radius: 16px`.
- Mega Editor dimensions: `width: min(1400px, 96vw)`, `height: min(92vh, 920px)`.

---

## 5. Layout Principles

- **Base Spacing Unit**: `4px` (`--s-1: 4px`, `--s-2: 8px`, `--s-3: 12px`, `--s-4: 16px`, `--s-5: 24px`, `--s-6: 32px`, `--s-7: 48px`).
- **App Shell Grid**: `grid-template-columns: 248px minmax(0, 1fr)` on desktop (`>= 1024px`).
- **Main Container**: `max-width: 1360px`, equal left and right padding `32px` (`16px` below `768px`), top `28px`, bottom `48px`.
- **Section Rhythm**: `24px` between major workgroup cards, `16px` grid gutters between peer cards, `12px` gaps inside control strips.
- **Alignment**: Strict left-edge vertical alignment across page header, mode cards, and content grids. Equal left and right content edges at every viewport width.

---

## 6. Depth & Elevation

Depth is created by **tonal surface luminance steps** and crisp **1px hairlines** — never soft blurred drop shadows on page cards.

| Tier | Z-Index | Surface | Border / Shadow | Use |
|---|---|---|---|---|
| **Level 0 — Canvas** | `0` | `#0A0A0B` | None | App canvas |
| **Level 1 — Shell & Cards** | `1` | `#0E0E10` / `#111113` | `1px solid rgba(255,255,255,0.08)` | Sidebar, studio cards, inspector panels |
| **Level 2 — Controls** | `2` | `#18181B` | `1px solid rgba(255,255,255,0.10)` | Inputs, chips, secondary buttons |
| **Level 3 — Floating UI** | `100` | `#141417` | `1px solid rgba(255,255,255,0.16)`, `0 16px 40px rgba(0,0,0,0.55)` | Modals, Mega Editor, Assistant drawer |
| **Level 4 — Notifications** | `200` | `#18181B` | `1px solid rgba(255,255,255,0.18)`, `0 10px 28px rgba(0,0,0,0.55)` | Toasts |

---

## 7. Do's and Don'ts (Strict Guardrails)

### Do
- Keep 92–95% of every screen neutral obsidian (`#0A0A0B`, `#111113`, `#18181B`) so video frames and subtitles carry all visual vibrancy.
- Use solid `--action` (`#FAFAFA` with `#09090B` ink in Obsidian default) for **at most one primary CTA per section/screen**.
- Use uniform `1.75px`-stroke monochrome SVG icons everywhere in the UI.
- Use `font-variant-numeric: tabular-nums` on every timer, percentage, duration, file size, and progress ring readout.
- Keep card nesting to **two boxes deep at most**; separate internal sections with `1px solid var(--border)` rules.
- Write plain, functional Russian studio copy: headings name the tool or section; buttons are verb + object (`Создать проект`, `Открыть видео`, `Перерендерить клип`).
- Use `color-mix(in oklab, ...)` when deriving tints from custom palette tokens.
- Keep semantic `<progress class="progress-ring">` with `conic-gradient()`, `background-clip: border-area`, `@supports not` `mask-image` fallback, `forced-colors`, and `prefers-reduced-motion`.

### Don't
- **NEVER use violet, purple, indigo, or lavender** (`#6366f1`, `#8b5cf6`, `#a855f7`, `#d946ef`, `#ec4899`) in the default theme, buttons, borders, glows, or ambient backgrounds.
- **NEVER place blurred neon radial-gradient blobs** (`body::before`) behind the studio interface.
- **NEVER put gradients on buttons** — primary buttons are flat solid fills (`var(--action)`).
- **NEVER use emojis** (`📁`, `🎨`, `🎙`, `✨`, `👤`, `⬜`, `▦`, `▶`, `🔊`) in buttons, cards, or inspector controls.
- **NEVER use AI marketing slop** ("Добро пожаловать в...", "магия ИИ", "вирусные клипы", "ультрабыстро").
- **NEVER apply `backdrop-filter` blur or heavy drop shadows** to regular page cards — keep surfaces crisp, opaque, and fast.
- **NEVER use `color-mix(in oklch, ...)` with neutrals** (Chromium bug 565837690).
- **NEVER exceed 4 border-radius tokens** (`4px`, `6px`, `8px`, `12px`, `16px` modal).

---

## 8. Responsive Behavior

| Breakpoint | Width | Layout Rules |
|---|---|---|
| **Wide Desktop** | `>= 1440px` | `248px` fixed sidebar + `1360px` max-width main container, 3-col mode cards, 2-col dashboard & new project, 2-col Mega Editor |
| **Desktop** | `1024px – 1439px` | `248px` sidebar, `24px` main horizontal padding, Mega Editor 2-col with fluid stage |
| **Tablet** | `768px – 1023px` | Sidebar collapses to compact top navigation bar (`height: auto`), Dashboard & New Project stack to 1 column, Mega Editor stacks stage above inspector |
| **Mobile / Narrow** | `<= 767px` | `16px` horizontal padding, 1-column grids, full-width primary buttons (`min-height: 44px`), touch targets `>= 44px × 44px` |

---

## 9. Agent Prompt Guide

### Quick-Reference Token Cheat Sheet
- **Canvas**: `#0A0A0B` | **Sidebar**: `#0E0E10` | **Card**: `#111113` | **Control**: `#18181B` | **Hover**: `#222226` | **Active**: `#27272A`
- **Text**: `#F4F4F5` | **Muted**: `#A1A1AA` | **Meta**: `#787882`
- **Borders**: `rgba(255,255,255,0.08)` default | `rgba(255,255,255,0.16)` hover | `rgba(255,255,255,0.32)` selected
- **Primary Action**: `#FAFAFA` bg / `#09090B` ink | **Signal**: `#0EA5E9` | **Warn/GPU**: `#F59E0B` | **Success**: `#22C55E` | **Danger**: `#EF4444`
- **Radii**: `4px` badge · `6px` input/chip · `8px` button/nav · `12px` card · `16px` modal
- **Spacing**: `4 / 8 / 12 / 16 / 24 / 32 / 48px`
- **Type**: `Inter` / `SF Pro` (`400 / 500 / 600`), `JetBrains Mono` / `tabular-nums` for telemetry

### Enforcement Prompt
> Build all KrlzCut UI strictly from `DESIGN.md`. Use `:root` CSS custom properties matching Section 2–6 verbatim. Keep 92–95% of every screen neutral obsidian (`#0A0A0B`/`#111113`/`#18181B`) with 1px hairlines, flat solid `#FAFAFA` primary buttons (`#09090B` ink), monochrome `1.75px` SVG icons, and plain Russian studio copy. Audit every edited file against Section 7 before finishing: zero violet/purple/lavender defaults, zero neon blobs, zero gradient buttons, zero emojis, zero box-in-box clutter.
