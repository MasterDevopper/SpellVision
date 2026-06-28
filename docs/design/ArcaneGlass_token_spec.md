# ArcaneGlass — ThemeManager token spec

Derived from the finalized Claude Design surfaces (10 `.dc.html` exports) and mapped onto
the **existing** `ThemeManager` accessors. This is an implementation reference for the
ArcaneGlass pass (after the Flows feature lands). It is a spec, not a patch — implement by
editing the `Preset::ArcaneGlass` branches in `ThemeManager.cpp`.

## The core correction (read this first)

`ThemeManager` already ships `Preset::ArcaneGlass` (enum value 0, the code default). Two
things are wrong, and they're the source of the "accents fighting" problem:

1. **`accentSecondary` is a blue (`#6f8cff`) and `accentTertiary` is a cyan (`#6fd3ff`),
   both used as decorative accents.** The design uses **one** hero accent (violet) and
   treats cyan as a **semantic ready/online signal only**. Fix the *roles*, not just the hex.
2. **The live app runs on Neon Forge**, because `QSettings appearance/themePreset` persisted
   a non-default choice. ArcaneGlass is already `Preset(0)`; shipping it means resetting that
   persisted value (or migrating it) so ArcaneGlass is what actually loads.

## Color tokens — design value → ThemeManager accessor → current → change

| ThemeManager accessor | Design value | Current ArcaneGlass | Change |
|---|---|---|---|
| `presetAccent()` (hero violet) | `#7C5CFF` (bright `#9A7DFF`) | `#8b6cff` | nudge to `#7C5CFF`; expose bright `#9A7DFF` for hover/active |
| `presetAccentSecondary()` | `#5B4BD6` (deep violet) | `#6f8cff` (blue) | **re-role to deep violet** — kills the blue clash |
| `presetAccentTertiary()` | `#C6B6FF` (violet highlight) | `#6fd3ff` (cyan) | **re-role to violet highlight** — cyan leaves the accent system entirely |
| `background0()` (void) | `#0A0B12` | `#090d14` | align to `#0A0B12` |
| `background1()` (page) | `#0D0F18` | `#101624` | align to `#0D0F18` |
| `surface0()` (panel) | `#13161F` | `#171f31` | align to `#13161F` |
| `surface1()` (elevated) | `#171B27` | `#20283c` | align to `#171B27` |
| `textPrimary()` | `#E9EBF4` | (verify) | set `#E9EBF4` |
| `textSecondary()` | `#9DA3B8` | (verify) | set `#9DA3B8` |
| `textMuted()` | `#646A82` | (verify) | set `#646A82` |
| `borderColor()` | `rgba(150,160,186,.14)` hairline; `.22` on hover/emphasis | (verify) | platinum-alpha hairline — the structural device |
| `inputSurface()` | `rgba(10,11,18,.55)` | (verify) | recessed input fill |
| `successColor()` / **ready** | `#34D6E6` (cyan) | (verify) | **this is where cyan lives** — ready/online/active only |
| `warningColor()` | `#E8B23A` (amber) | (verify) | needs-attention |
| `errorColor()` | red (existing fine) | — | keep |

Supporting structural hexes (not necessarily accessors — use inline where the metal-frame
look is needed): platinum highlight `#C3C9DC` / `#E4E8F4`, steel `#8B92A8` / `#9AA2B8`,
steel-deep `#5C6480`. Iris-glow stops for the brand mark: `#EDE9FF`, `#C6B6FF`, `#7C5CFF`,
`#3A2F8C`.

## Type tokens

| Role | Face | Use |
|---|---|---|
| Display / brand | Space Grotesk (500/600) | app name, page H1, hero moments |
| UI / body | Inter (400/500) | all dense UI, labels, controls |
| Data / mono | JetBrains Mono (400/500) | VRAM, seed, dimensions, hashes, queue counts |

Sentence case everywhere. Two weights per face. (Qt: register the .ttf/.otf via
`QFontDatabase::addApplicationFont` so the app doesn't depend on system-installed fonts.)

## Radii

Design uses `6px` (small / inputs, chips), `9px` (medium / most panels & buttons — the
dominant value), `13px` (large / cards & canvas). Map these to the radius mechanism in
`ThemeManager`. NOTE: my read of `ThemeManager.h` found the `Preset` enum and
`effectsWeight_` but did **not** surface the `Spacing`/`Chrome` token enums that should
exist — locate them when implementing and confirm whether radius is tokenized there or
applied per-widget. Don't invent a radius enum if one already exists under another name.

## Qt rendering notes (design → widgets)

- **Glass ≠ backdrop-blur.** Qt won't replicate CSS `backdrop-filter` cheaply. Approximate
  the glass panels with a layered solid fill (e.g. `surface0` at ~85–90% over `background1`)
  plus a 1px platinum-alpha top/left highlight border. Don't chase real blur.
- **Glow** (violet on active rail item, Generate button, focus rings) → a soft outer
  `box-shadow` equivalent via `QGraphicsDropShadowEffect` **used sparingly**, or a painted
  border-glow in a custom `paintEvent`. Spend it only on the hero accent, per the design.
- **`effectsWeight_`** (currently 68) already exists as a global intensity dial — wire glow
  strength and border energy to it so the "Effects Intensity" slider in Settings stays live.
- Gradients exist in the design only on the Generate button and the brand mark; keep
  everything else flat-filled.

## Definition of done for the ArcaneGlass pass

1. `Preset::ArcaneGlass` color branches retuned to the table above, with cyan moved out of
   the accent roles into the semantic/ready slot.
2. App actually boots on ArcaneGlass (persisted-preset reset/migration handled).
3. Fonts registered and applied across the three roles.
4. One reference surface (the cockpit / T2I) visually matched to its `.dc.html` and
   screenshotted for comparison before rolling the tuning across the rest.
