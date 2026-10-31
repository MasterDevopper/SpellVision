# Slice 1 methodology — cockpit material

Written so the next session can repeat the method, not copy the diff blindly.

## What slice 1 is

Doc 64 slice 1: on the generation cockpit, work surfaces are matte and the preview well is the only glass. No copy changes. No new theme, no new `ThemeManager::Color`, no page moved.

## What was already true, and why a global style flip was the wrong fix

`ThemeManager::Style` already has `RefinedGlass`, `MatteInstrument`, and `Hybrid`. `styleUsesGlass(hero)` is the hinge:

- RefinedGlass glasses every surface.
- MatteInstrument glasses none.
- Hybrid glasses hero surfaces only (`Glass` and `Plate`).

The app default is RefinedGlass. Ember and the other presets must keep working, and `appearance/themePreset` must not be migrated. Flipping the global style would restyle Home, Models, studios, and Settings. Slice 1 is the cockpit only.

`SvStyle::paintSurface` was the only painter for `svSurface`. It asked `styleUsesGlass(hero)` and, on glass, also painted a radial glow. There was no per-widget override. A search for `svForceMatte` / `svMaterial` returned nothing.

## The constraint that decided the structure

`tests/cpp/test_shell_layout.cpp` requires the action row to stay the canvas card's footer. Moving the row out of `CanvasCard` to "make the card glass and the row matte" would fail that test and assert a move. The glass had to move inward.

So:

- `CanvasCard` is `Surface::Panel` (the work surface that owns the session strip and the action row).
- A new `PreviewWell` frame, `Surface::Glass`, wraps `previewArea_` and is the only glass child of that card.
- The action row stays the last widget in `canvasLayout`.

## The override

`ImageGenerationPage::buildUi` sets `svCockpitMatte` on the page. `paintSurface` walks `parentWidget()` for that property.

When it finds it:

- `Surface::Glass` paints the spec glass path: one fill, one border, one top highlight. No radial.
- If `GlassFill` has been flattened to solid (Matte Instrument does this, and zeroes `GlassHighlight`), the well does not read those tokens. It paints `Surface0` at alpha 220 and a `TextHi` hairline at alpha 46. Otherwise the well uses the style's own glass tokens.
- Every other surface paints the matte branch: `Surface0` for inset, `Surface1` otherwise, one border. No plate highlight.

Pages that do not set the property are unchanged. That is why the existing Refined/Hybrid/Matte pixel test still means what it meant.

`#CockpitInspector` was a second sun: a QSS vertical gradient of `@cardTop@` to `@cardBottom@`, which `SvStyle` never sees. That one rule is now a flat `@cockpitMatte@`, replaced with `color(Color::Surface1).name()` (opaque). Not a new color role. Not a `%N`.

## What was deliberately not touched

- Copy, 9px chips, Generate, inspector tab chrome, plate rim animation. Those are later slices.
- The empty-canvas radial is a `QLabel` stylesheet, not a card `paintEvent`. Slice 1 deletes radials in card paint. That label stays for the plate slice.
- Home, Models, studios, Settings, rail, title bar.
- `appearance/themePreset` and `appearance/surfaceStyle`.

## How to know it worked

`tests/cpp/test_sv_style.cpp` `cockpit_matte_overrides_refined_glass`:

- A panel under a `svCockpitMatte` parent, with the app style still RefinedGlass, differs from a free RefinedGlass panel by at least 10% of pixels.
- The glass well is not separated from the matte panel by area percent under RefinedGlass. `GlassFill` composites to within 8 channel levels of `Surface1`, so a 10% area gate fails at about 1% (the highlight line only). The lock is the top highlight pixel at `(80, 1)`.
- Under MatteInstrument the same well must still differ from a cockpit panel by at least 10% of pixels. That is the unflatten. Without it the well is solid `Surface1` and the slice is invisible on a Matte machine.

Run (Debug, Qt debug DLLs on PATH):

```
cmake --build build --config Debug --target test_sv_style
```

From `build/Debug`, with `C:\Qt\6.10.2\msvc2022_64\bin` on PATH:

```
test_sv_style.exe cockpit_matte_overrides_refined_glass -v2
```

Git-bash will not run that exe (exit 127, no output). Use `C:\Windows\System32\cmd.exe /c` and a log file via `-o path,txt`. A silent exit 1 with no log is a missing `Qt6Testd.dll`, not a failed assert.

On screen, T2I with no image: one glass region, the preview well. Prompt card, action row, inspector, asset intelligence, and LoRA rows are opaque. Ember still applies. Contrast was not measured.

## Files

- `qt_ui/style/SvStyle.cpp` — `paintSurface` takes the widget and honors `svCockpitMatte`.
- `qt_ui/ImageGenerationPage_ui.cpp` — property, `CanvasCard` panel, `PreviewWell` glass.
- `qt_ui/ThemeManager.cpp` — inspector shell fill, `@cockpitMatte@` replace.
- `tests/cpp/test_sv_style.cpp` — the lock above.

## Next slice

Slice 2. Kill 9px instructions. Do not reopen material.
