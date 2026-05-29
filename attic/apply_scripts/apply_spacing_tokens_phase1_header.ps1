$patch = @'
"""
Spacing Tokens Phase 1 (header): add the spacing/sizing token API.

This is the FOUNDATION pass. It adds a spacing/sizing vocabulary to
ThemeManager so that pages can stop inventing their own margin and
spacing literals. This patch is purely additive -- it defines the
tokens and their accessors. It changes NO behavior and migrates NO
pages. Migration happens in Phase 2, one surface at a time.

Design, matched to the existing ThemeManager idiom:

  - ThemeManager is a QObject singleton accessed via instance(). The
    token accessors are plain public const methods returning int,
    exactly like the existing QColor accessors return QColor.

  - Spacing does NOT vary by preset. Only *color* changes per theme;
    the spacing rhythm is constant. So unlike background0()/surface0()
    which switch on preset_, these accessors return fixed values.

  - Two enums:
      Spacing  -- the 4/8/12/16/24/32 scale, named by role at the call
                  site (Hairline / Tight / Snug / Card / Section /
                  Gutter). Named-by-role rather than by-number so a
                  later global tuning is a one-place change.
      Chrome   -- fixed structural heights the shell currently hard-codes
                  as magic literals (title bar, menu bar, status strip,
                  telemetry bar, mode-rail width).

  - Radius accessors (radiusCard / radiusControl / radiusPill) round out
    the set -- corner radius is the other thing every card reinvents.

Phase 2 will migrate T2I and Settings first (they are already the
cleanest surfaces) to validate the vocabulary on real pages before
going wide to MainWindow / ImageGenerationPage.
"""
from pathlib import Path
path = Path("qt_ui/ThemeManager.h")
text = path.read_text(encoding="utf-8")

# --- Insertion 1: the two enums, right after the Preset enum block ---
enum_needle = '''    enum class Preset
    {
        ArcaneGlass = 0,
        ObsidianStudio,
        NeonForge,
        IvoryHolograph
    };
    Q_ENUM(Preset)'''

enum_replacement = '''    enum class Preset
    {
        ArcaneGlass = 0,
        ObsidianStudio,
        NeonForge,
        IvoryHolograph
    };
    Q_ENUM(Preset)

    // --- Spacing Tokens Phase 1 ---
    // Named-by-role spacing scale. Values are constant across presets
    // (only color changes per theme). Use spacing(Spacing::Card) at call
    // sites instead of literal margins, so a later tuning is one edit.
    enum class Spacing
    {
        Hairline = 0,   // 4px  - icon/label gaps, the smallest seam
        Tight,          // 8px  - control-to-control inside a row
        Snug,           // 12px - label-to-control, intra-card stacking
        Card,           // 16px - card content padding, the default unit
        Section,        // 24px - between major sections within a column
        Gutter,         // 32px - page-level gutters, large separations
    };
    Q_ENUM(Spacing)

    // Fixed structural chrome heights/widths the shell currently
    // hard-codes. Centralizing them here means the title bar, status
    // strip, telemetry bar etc. all read from one source.
    enum class Chrome
    {
        TitleBarHeight = 0,   // 32px
        MenuBarHeight,        // 40px
        StatusStripHeight,    // 24px
        TelemetryBarHeight,   // 30px
        ModeRailWidth,        // 76px
    };
    Q_ENUM(Chrome)'''

if enum_needle not in text:
    raise SystemExit("Could not find the Preset enum block in ThemeManager.h")
text = text.replace(enum_needle, enum_replacement, 1)

# --- Insertion 2: the accessor declarations, grouped with the other
#     public value accessors. Anchor on effectsWeight() which is the
#     last of the simple int/bool accessors before the setters. ---
accessor_needle = '''    QColor accentTertiary() const;
    int effectsWeight() const;'''

accessor_replacement = '''    QColor accentTertiary() const;
    int effectsWeight() const;

    // --- Spacing Tokens Phase 1: token accessors ---
    // Plain const int accessors, matching the shape of the QColor
    // accessors above. No preset switch -- spacing is theme-invariant.
    int spacing(Spacing token) const;
    int chrome(Chrome token) const;
    int radiusCard() const;
    int radiusControl() const;
    int radiusPill() const;'''

if accessor_needle not in text:
    raise SystemExit("Could not find the effectsWeight() accessor anchor in ThemeManager.h")
text = text.replace(accessor_needle, accessor_replacement, 1)

path.write_text(text, encoding="utf-8")
print("Applied Spacing Tokens Phase 1 (header): Spacing/Chrome enums + accessors declared.")
'@
Set-Content .\scripts\refactors\apply_spacing_tokens_phase1_header.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_spacing_tokens_phase1_header.py
