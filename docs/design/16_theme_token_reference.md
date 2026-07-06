# Doc 16 — Theme Token Reference (canonical color tokens)

The single, named color ramp every SpellVision widget migrates to. This is the
source of truth for the multi-theme migration (Phases 1–8). A **theme = one value-set
for these tokens**; switching swaps the set and emits `ThemeManager::themeChanged()`.

- **Read tokens, never literals.** `ThemeManager::instance().color(Color::X)` returns a
  `QColor` (for `QPainter`/`QPen`/`QBrush`); `.css(Color::X)` returns a Qt stylesheet
  string (`#RRGGBB` when opaque, `rgba(r,g,b,a)` when translucent).
- Enum + accessors live in `qt_ui/ThemeManager.h` (`enum class Color`), values in
  `ThemeManager::rebuildColorTokens()` (`qt_ui/ThemeManager.cpp`).
- Spacing / radius / chrome tokens are unchanged (earlier sprint) — this reference
  covers **color** only.

## The pattern (every phase applies this per-widget)

A themed widget owns an `applyThemeStyling()` (or `applyTheme()`) method that reads
**tokens** and sets its local stylesheet + any paint colors, and it **subscribes** to
`themeChanged`:

```cpp
// in the widget ctor:
applyThemeStyling();
connect(&ThemeManager::instance(), &ThemeManager::themeChanged,
        this, &Widget::applyThemeStyling);
```

`applyThemeStyling()` re-reads `color()`/`css()` and re-sets stylesheet/pixmaps, then
`update()` for painted widgets. This per-widget subscription is what makes a widget
switch live — a widget only re-colors once it is migrated **and** subscribed.

> **Gotcha (shell-styled elements):** if an element is colored by the shell stylesheet
> via its object name (an ancestor `#ObjectName { color: … }` rule), a local override
> loses to that ancestor ID rule *regardless of local specificity*. Migrating such an
> element means the widget **takes over its own theming** — detach it from the shared
> generator (e.g. clear/replace the object name) and style it locally from tokens.
> (Seen on the pilot's search-pill labels.)

## Canonical color tokens — 24, with ArcaneGlass values

| Token | ArcaneGlass value | Role |
|---|---|---|
| `Surface0` | `#0A0B12` | app background (darkest) |
| `Surface1` | `#13161F` | panels / cards |
| `Surface2` | `#171B27` | raised surfaces |
| `Surface3` | `#1D2230` | overlays / drawer |
| `TextHi` | `#E9EBF4` | primary text |
| `TextMid` | `#9DA3B8` | secondary text |
| `TextLo` | `#646A82` | muted text |
| `TextDisabled` | `#454A5E` | disabled text |
| `Accent` | `#7C5CFF` | hero violet |
| `AccentHover` | `#9A7DFF` | hover |
| `AccentActive` | `#6B4AE8` | pressed |
| `AccentDisabled` | `#4A4470` | disabled accent |
| `AccentGlow` | `rgba(124,92,255,90)` | glow over surfaces |
| `AccentSubtle` | `rgba(124,92,255,26)` | tint fills |
| `Border` | `rgba(150,160,186,36)` | hairline (~.14 platinum) |
| `BorderStrong` | `rgba(150,160,186,56)` | emphasis / hover (~.22) |
| `BorderSubtle` | `rgba(150,160,186,20)` | faintest (~.08) |
| `Success` | `#34D6E6` | ready/online — **the only cyan** |
| `Warning` | `#E8B23A` | needs attention |
| `Error` | `#D85D73` | error |
| `Info` | `#4C9AE6` | informational (no audit source; blue distinct from success/accent) |
| `GlassFill` | `rgba(19,22,31,220)` | translucent panel fill (glass identity) |
| `GlassGlow` | `rgba(124,92,255,40)` | accent glow over glass |
| `GlassHighlight` | `rgba(196,201,220,30)` | platinum top-edge highlight |

Derivation: ArcaneGlass values are the authored design values (from the finalized
Claude Design surfaces + `ArcaneGlass_token_spec.md`). The accent family was already
retuned in `ThemeManager` (violet, cyan moved to `Success`); surfaces/text here are the
design values and are the **go-forward truth** — the *legacy* per-preset accessors
(`surface0()`/`textPrimary()`/…) still hold the pre-migration (slightly drifted) values
that not-yet-migrated stylesheet generators use, and are reconciled to these as each
generator migrates.

## Hardcoded-color → token migration map (the common cases)

| Hardcoded literal(s) | → Token |
|---|---|
| `#9DA3B8` (most frequent) | `TextMid` |
| `#E9EBF4` | `TextHi` |
| `#646A82` | `TextLo` |
| `#7C5CFF`, `rgba(124,92,255,x)` | `Accent` (or `AccentGlow`/`AccentSubtle` by alpha) |
| `#9A7DFF` | `AccentHover` |
| `#34D6E6` | `Success` |
| `#0A0B12`, `#090d14` | `Surface0` |
| `rgba(150,160,186,x)`, `#96A0BA` | `Border` / `BorderStrong` / `BorderSubtle` by alpha |
| `#03060d`, `#071120`, `#01040a`, `#02050b` (paint darks) | `Surface0` / behind-glass darks |
| `#9ff5ca` / `#ffd1dc` (readiness good/bad) | reconcile → `Success` / `Error` (soft variants TBD) |

## Themes

`ThemeManager` has slots for **N** themes; a new theme = a value-column for these 24
tokens. Registered via `Preset` (enum) + `presetNames()` + a branch in
`rebuildColorTokens()`. Present slots: `ArcaneGlass` (authored), `ObsidianStudio` /
`NeonForge` / `IvoryHolograph` (legacy value-sets, derived into canonical tokens until
art-directed), and **`_TestSwitching`** — a *throwaway* garish orange-on-navy proof
palette used to verify the switch mechanism (removed once a real 2nd theme is authored).
The real 2nd-theme palette is a pending art-direction decision, not an architecture one.

## Status

- **Phase 1 (foundation) — DONE.** Token API + `themeChanged` broadcast + the switch
  wired (Settings preset dropdown → `setPresetByIndex`) + pilot (`CustomTitleBar`:
  icons/badge = paint case, search labels = string case). Verified live: pilots switch
  ArcaneGlass↔TEST with no restart; non-pilot surfaces stay put (per-widget subscription).
- **Phases 2–8** migrate the ~150 remaining hardcoded color occurrences (15 files),
  worst-first, each widget adopting the pattern above.
