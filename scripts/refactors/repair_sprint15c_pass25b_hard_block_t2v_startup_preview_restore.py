from pathlib import Path
import re

h_path = Path("qt_ui/ImageGenerationPage.h")
cpp_path = Path("qt_ui/ImageGenerationPage.cpp")
hist_path = Path("qt_ui/T2VHistoryPage.cpp")
doc_path = Path("docs/sprints/SPRINT15C_PASS25B_HARD_BLOCK_T2V_STARTUP_PREVIEW_RESTORE_README.md")
script_path = Path("scripts/refactors/repair_sprint15c_pass25b_hard_block_t2v_startup_preview_restore.py")

h = h_path.read_text(encoding="utf-8")
cpp = cpp_path.read_text(encoding="utf-8")
hist = hist_path.read_text(encoding="utf-8")

# Add state flag.
if "suppressStartupVideoPreviewRestore_" not in h:
    h = h.replace(
        "    QString generatedPreviewCaption_;\n",
        "    QString generatedPreviewCaption_;\n"
        "    bool suppressStartupVideoPreviewRestore_ = false;\n",
        1,
    )

# Set suppression before/after snapshot restore for video modes.
old = '''    reloadCatalogs();
    restoreSnapshot();

    // Sprint 15C Pass 25:
    // Restoring the last generated video into T2V on startup is not intended.
    // Keep restored controls/prompts, but do not bind media automatically.
    // Users can still open History or Queue to inspect prior outputs explicitly.
    if (isVideoMode())
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();

        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();
    }

    updateAdaptiveLayout();
    updatePrimaryActionAvailability();
    schedulePreviewRefresh(busy_ ? 0 : 30);
'''

new = '''    reloadCatalogs();

    if (isVideoMode())
        suppressStartupVideoPreviewRestore_ = true;

    restoreSnapshot();

    // Sprint 15C Pass 25B:
    // Restoring the last generated video into T2V on startup is not intended.
    // Keep restored controls/prompts, but do not bind persisted media automatically.
    // Users can still open History or Queue to inspect prior outputs explicitly.
    if (isVideoMode())
    {
        generatedPreviewPath_.clear();
        generatedPreviewCaption_.clear();

        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();
    }

    updateAdaptiveLayout();
    updatePrimaryActionAvailability();

    if (!isVideoMode())
        schedulePreviewRefresh(busy_ ? 0 : 30);
    else
        refreshPreview();
'''

if old not in cpp:
    raise SystemExit("Could not find Pass 25 constructor block to upgrade.")

cpp = cpp.replace(old, new, 1)

# Patch refreshPreview guard near function opening.
match = re.search(r'void ImageGenerationPage::refreshPreview\(\)\s*\{', cpp)
if not match:
    raise SystemExit("Could not find refreshPreview().")

guard = '''
    if (isVideoMode() && suppressStartupVideoPreviewRestore_)
    {
        if (mediaPreviewController_)
            mediaPreviewController_->clearVideoPreview();

        if (previewStack_ && previewImagePage_)
            previewStack_->setCurrentWidget(previewImagePage_);

        if (previewLabel_)
        {
            previewLabel_->setProperty("emptyState", true);
            previewLabel_->setText(QStringLiteral("No video preview loaded yet. Generate a video or choose one from History."));
        }

        return;
    }

'''

insert_at = match.end()
if "No video preview loaded yet. Generate a video or choose one from History." not in cpp:
    cpp = cpp[:insert_at] + guard + cpp[insert_at:]

# Clear suppression only when app explicitly receives/sets a preview path, not during restore.
# setPreviewImage is for image; showVideoPreviewSurface is the explicit video binder.
show_match = re.search(r'void ImageGenerationPage::showVideoPreviewSurface\(const QString &videoPath, const QString &caption\)\s*\{', cpp)
if show_match and "suppressStartupVideoPreviewRestore_ = false;" not in cpp[show_match.end():show_match.end()+400]:
    cpp = cpp[:show_match.end()] + "\n    suppressStartupVideoPreviewRestore_ = false;\n" + cpp[show_match.end():]

# If generatedPreviewPath_ is assigned after worker result, that should also allow preview refresh.
# Add a broad but guarded repair for common assignment statements.
cpp = cpp.replace(
    "    generatedPreviewPath_ = path;\n",
    "    suppressStartupVideoPreviewRestore_ = false;\n    generatedPreviewPath_ = path;\n",
    1,
)

# Update T2V contract builder state to use preferred output status and not stale full output fields.
# This ensures the next successful requeue contract writes D output.
if "const QJsonObject preferredUiOutput = preferredLtxUiOutputObject(uiOutputs);" in hist:
    hist = hist.replace(
        '''    const QString outputPath = stringFromObjectPath(output, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("uri"),
    });
''',
        '''    const QString outputPath = stringFromObjectPath(output, {
        QStringLiteral("path"),
        QStringLiteral("preview_path"),
        QStringLiteral("uri"),
    });
''',
        1,
    )

h_path.write_text(h, encoding="utf-8")
cpp_path.write_text(cpp, encoding="utf-8")
hist_path.write_text(hist, encoding="utf-8")

doc_path.parent.mkdir(parents=True, exist_ok=True)
doc_path.write_text(
    "# Sprint 15C Pass 25B — Hard Block T2V Startup Preview Restore\n\n"
    "Adds a startup suppression flag so T2V does not automatically bind the previously generated video during app launch or initial page creation.\n\n"
    "The first T2V page render now shows an empty video preview state. Preview binding is re-enabled only when a video is explicitly shown by generation, history, or queue action.\n\n"
    "This also keeps the Pass 25 distilled-output preference in T2V History.\n",
    encoding="utf-8",
)

script_path.write_text(Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() else "", encoding="utf-8")

print("Applied Pass 25B hard block for T2V startup preview restore.")
