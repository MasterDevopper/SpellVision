"""
Sprint V Pass 1-FIX: relocate VideoFamily method declarations.

Pass 1 placed the four VideoFamily helper declarations immediately after
usesWanDualNoiseMode(), which sits in a PUBLIC method-declaration region
ABOVE the line where `enum class VideoFamily` is declared (private region,
near videoComponentPanel_).

C++ is parsed top-to-bottom, so at the method-declaration site the
compiler had not yet seen the VideoFamily type. Result: a cascade of
C3646 "unknown override specifier" / C2059 syntax errors.

This fix:
  1. Removes the misplaced method block from the public region.
  2. Re-inserts it immediately AFTER the enum + card-field block so the
     type is in scope when the declarations are parsed.

Idempotency: if the misplaced block is already gone (e.g. this fix was
already run), step 1 is skipped rather than failing.
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.h")
text = path.read_text(encoding="utf-8")

# --- Step 1: remove the misplaced method block from the public region ---
#
# This is exactly what Pass 1's insertion2 produced. We strip it back to
# just the original usesWanDualNoiseMode() line.

misplaced = '''    bool usesWanDualNoiseMode() const;

    // Sprint V Pass 1: family resolution + UI sync helpers.
    VideoFamily videoFamilySelection() const;
    VideoFamily resolvedVideoFamily() const;
    QString resolvedVideoFamilyToken() const;
    void updateVideoFamilyUi();'''

restored = '''    bool usesWanDualNoiseMode() const;'''

if misplaced in text:
    text = text.replace(misplaced, restored, 1)
    removed = True
else:
    removed = False

# --- Step 2: re-insert the method block AFTER the enum + card fields ---
#
# Pass 1's insertion1 produced the enum block ending with videoFamilyCombo_
# then videoComponentPanel_. We anchor on that and insert the methods just
# after videoFamilyCombo_, still inside the class, with the type in scope.
#
# NOTE: even though these are private here (they were public before), they
# are only ever called from within ImageGenerationPage's own .cpp, so
# private visibility is correct and matches the other video helpers like
# updateVideoStackModeUi() which are also effectively internal.

enum_anchor = '''    QWidget *videoFamilyCard_ = nullptr;
    QComboBox *videoFamilyCombo_ = nullptr;
    QWidget *videoComponentPanel_ = nullptr;'''

if enum_anchor not in text:
    raise SystemExit(
        "Could not find the VideoFamily enum/card-field block from Pass 1. "
        "Was Pass 1 applied? Header may be in an unexpected state."
    )

enum_anchor_with_methods = '''    QWidget *videoFamilyCard_ = nullptr;
    QComboBox *videoFamilyCombo_ = nullptr;

    // Sprint V Pass 1-FIX: family resolution + UI sync helpers.
    // Declared here (after the VideoFamily enum) so the type is in scope.
    VideoFamily videoFamilySelection() const;
    VideoFamily resolvedVideoFamily() const;
    QString resolvedVideoFamilyToken() const;
    void updateVideoFamilyUi();

    QWidget *videoComponentPanel_ = nullptr;'''

# Guard against double-application: if the methods are already here, stop.
if "VideoFamily videoFamilySelection() const;" in text and not removed:
    # Methods already relocated and misplaced block already gone.
    print("Sprint V Pass 1-FIX: header already in fixed state, no change needed.")
else:
    text = text.replace(enum_anchor, enum_anchor_with_methods, 1)
    path.write_text(text, encoding="utf-8")
    print("Applied Sprint V Pass 1-FIX: VideoFamily method declarations relocated below the enum.")
