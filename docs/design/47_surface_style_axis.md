# 47 — Surface styles: three materials over five palettes

**Status:** shipped on `wave/rebuild-and-audit-fixes`. Settings → **Surface Style**.

The design pass produced three rival directions (Doc: `mockup_review.md`). Rather than pick one and
throw two away, they are built as a **style axis** that composes with the existing colour presets.

---

## 1. The model

Two independent axes, the same shape as `AnimationQuality`, which the header already documents as
orthogonal to the theme:

| axis | owns | values |
|---|---|---|
| `Preset` | the **hues** — surfaces, text, accent, status | Arcane Glass, Obsidian Studio, Neon Forge, Ivory Holograph, Ember |
| `Style` | the **material** — translucency, glow, hairline weight, radius | Refined Glass, Matte Instrument, Hybrid |

15 valid pairings, all art-directed by construction rather than by hand: `rebuildColorTokens()` is
split into `rebuildPresetColorTokens()` (hues) then `applyStyleToColorTokens()` (material). A preset
never has to know which style is active, and a style never has to know the palette.

Persisted at `appearance/surfaceStyle`. Default **Refined Glass** — the closest to what shipped, so
an update never silently restyles someone's app.

## 2. The three materials

| | Refined Glass | Matte Instrument | Hybrid |
|---|---|---|---|
| body | translucent, gradient | opaque, flat | opaque (hero: glass) |
| light sources | one, the accent | none | one, hero only |
| paint ops per panel | 4 | 2 | 2 (hero: 4) |
| card / control radius | 10 / 6 | 6 / 4 | 8 / 5 |
| hairline | palette value | ×1.45 | ×1.25 |
| `Surface0` | palette value | deepened one step | palette value |

**Five of the nine paint layers were deleted** from `DashboardGlassPanel::paintEvent`:

- the **hero side-glow** — a second light source on the one surface that already had the main one;
- the **per-panel vignette** — it darkened every card's own bottom edge, fighting the elevation the
  surface tokens set;
- the **decorative `drawArc` sheen** — an arc of light corresponding to no geometry, the single most
  consumer-skin move in the stack;
- the **rim streak** — a repeat of the specular wash it sat on top of.

Matte is a **separate function** (`paintMatte`), not a flag threaded through the glass stack. They
are different materials, not one material at a lower setting.

## 3. Palettes: what "polished" meant

Obsidian Studio, Neon Forge and Ivory Holograph were *algorithmically derived* from a handful of
accessors. Ivory suffered worst, because on a light ground every relationship inverts: surfaces get
lighter as they rise, text darkens, and a glow that reads as light on black reads as dirt on white.
All three are now authored token blocks alongside ArcaneGlass and Ember, with Ivory given dark
hairlines and a near-white frost instead of a glow.

### The accent ramps are solved, not picked

Every shade a button can be filled with has two constraints that pull in opposite directions:

- the **white label** on it must clear **4.5:1** (AA text);
- the fill must stay **≥3:1** against its own surface, or the control is not findable.

The natural-looking candidate `#5B8DEF` reads beautifully on the surface (**5.61**) while its own
label sits at **3.23** — the exact flaw the independent review found in two of the three mockups.
The band that satisfies both is narrow and was searched numerically rather than eyeballed:

| preset | Accent | white label | on Surface1 |
|---|---|---|---|
| Obsidian Studio | `#3568D0` | 5.20 | 3.49 |
| Neon Forge | `#B425C1` | 5.28 | 3.50 |
| Ivory Holograph | `#5A3FD6` | 6.74 | 6.44 |

The vivid shades survive where they are never a text background — `#5B8DEF` and `#E040FB` are the
hover and tertiary/glow values.

## 4. Two traps, both real

**`withAlpha()` sets an absolute alpha, not a multiplier.** The style pass needs "make this preset's
hairline half again as strong" to work across five palettes that each chose a different starting
alpha. `withAlpha(border, 1.45)` clamps to 1.0 and paints an **opaque bar where a hairline belongs**.
`scaleAlpha()` was added for this.

**Never add a `%N` placeholder to `shellStyleSheet`.** It is a **62-argument** `QString::arg` call,
and `arg()` resolves by the *lowest* remaining placeholder — inserting one renumbers every later one,
which is the mechanism behind the 2026-07-25 "lavender void" incident. Two safe seams were used
instead:

- **named tokens** in the existing `@token@` replace chain, for the radii (20 literals → `@rcard@` /
  `@rctl@`);
- **argument values**, for the panel fills — `panelFillCss()` changes what an existing `%N` *is*,
  without touching the sheet text at all.

## 5. What the assert does and does not cover

`ThemeManager::runContrastSelfCheck()` is a **`Q_ASSERT_X`**, not a lint. A failing hex does not
warn — it aborts a Debug build at `ThemeManager` construction, before the window shows. It now walks
**style × preset**, not preset alone.

Its coverage is `TextHi/Mid/Lo ≥ 4.5:1` and `TextDisabled ≥ 3.0:1` against `Surface0..2` — the
**tokens**. That is why `panelFillCss()` does not lighten the matte fill even though a lift would
separate it further: a colour derived at paint time is outside the assert's coverage, so lifting it
would be an unguarded change to a surface real text sits on. Separation comes from deepening
`Surface0` in the style pass, which the assert does see.

**Verified by running the app on each style: 0 contrast warnings, no abort, all 15 pairings.**

## 6. Measured effect

Mean per-pixel difference on Home, Arcane Glass:

| pair | mean |
|---|---|
| glass ↔ matte | 2.50 |
| glass ↔ hybrid | 1.89 |
| matte ↔ hybrid | 0.62 |

By region, glass vs matte: left rail 2.26, title bar 2.14, bottom bar 2.26, Home panels 2.25 — the
material lands **uniformly across the shell**, not only on `DashboardGlassPanel`.

Honest reading of those numbers: ~2.2/255 is a restrained material change, not a dramatic reskin.
Matte and Hybrid are close on Home specifically because Home has no `Variant::Hero` panel, which is
the surface Hybrid exists to treat differently.

## 7. Remaining

- **Interaction states.** The review's finding that the build has *no* hover/active/focus states at
  all is still true — this pass changed the material, not the states. It is the single largest
  remaining gap and applies to all three styles.
- **`imageGenerationStyleSheet`** (46 args) still has its own radius literals; only the shell sheet
  was tokenised.
- **Hybrid needs hero surfaces.** It only differs from Matte where a `Variant::Hero` panel exists.
  The cockpit canvas is the obvious candidate.
- Four pages carry hardcoded `rgba(10,11,18,0.55)` (`InspirationPage`, `TrainPage`, `Gen3DPage`,
  `DatasetGenerationPage`) — a cross-theme bug that renders dark inputs on Ivory, unchanged here.
