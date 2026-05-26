"""
Sprint V Pass 1: VideoFamily enum + card field declarations.

Adds the VideoFamily enum (LTX / WAN / Auto), a card-widget pointer for
the new top-of-rail family selector, and helper method signatures.

The actual implementation lands in Pass 2 (card construction + visibility
gating) and Pass 3 (WAN advanced rows + Components panel family-awareness).
"""
from pathlib import Path
path = Path("qt_ui/ImageGenerationPage.h")
text = path.read_text(encoding="utf-8")

# --- Insertion 1: VideoFamily enum + helper signatures, near other enums/methods ---

needle1 = '''    QWidget *videoComponentPanel_ = nullptr;
    QWidget *videoStackModeRow_ = nullptr;
    QWidget *videoHighNoiseRow_ = nullptr;
    QWidget *videoLowNoiseRow_ = nullptr;
    QComboBox *videoStackModeCombo_ = nullptr;'''

replacement1 = '''    // Sprint V Pass 1: VideoFamily separates LTX vs WAN as a first-class
    // user choice. Auto resolves from the currently selected checkpoint via
    // resolvedVideoFamily(); the existing suggestedVideoStackMode() helper
    // already knows how to inspect modelFamilyByValue_ + path hints.
    enum class VideoFamily
    {
        Auto,
        Ltx,
        Wan,
    };

    QWidget *videoFamilyCard_ = nullptr;
    QComboBox *videoFamilyCombo_ = nullptr;
    QWidget *videoComponentPanel_ = nullptr;
    QWidget *videoStackModeRow_ = nullptr;
    QWidget *videoHighNoiseRow_ = nullptr;
    QWidget *videoLowNoiseRow_ = nullptr;
    QComboBox *videoStackModeCombo_ = nullptr;'''

if needle1 not in text:
    raise SystemExit("Could not find videoComponentPanel_ declaration in header")
text = text.replace(needle1, replacement1, 1)

# --- Insertion 2: helper method declarations, near other Q_INVOKABLE/helpers ---
# Look for an existing helper as anchor, then insert after it.

needle2 = '''    bool usesWanDualNoiseMode() const;'''

if needle2 not in text:
    raise SystemExit("Could not find usesWanDualNoiseMode declaration in header")

replacement2 = '''    bool usesWanDualNoiseMode() const;

    // Sprint V Pass 1: family resolution + UI sync helpers.
    VideoFamily videoFamilySelection() const;
    VideoFamily resolvedVideoFamily() const;
    QString resolvedVideoFamilyToken() const;
    void updateVideoFamilyUi();'''

text = text.replace(needle2, replacement2, 1)

path.write_text(text, encoding="utf-8")
print("Applied Sprint V Pass 1: VideoFamily enum + signatures added to header.")
