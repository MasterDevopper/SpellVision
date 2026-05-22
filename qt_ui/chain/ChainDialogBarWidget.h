#pragma once

// SpellVision — Chain Studio top dialog bar (Pass 7d.2).
//
// The 56px row above the rail. Per the v3 mockup's .dialog-line:
//
//   [ upload box 56x56 ]  [ dialog bar — flex ]  [ + add stage 104px ]
//
// Components:
//
// 1. Upload box: clickable 56x56 frame. Empty state shows a small "⤒"
//    glyph + "IMG" caption with a dashed border. When an image is set,
//    the box shows a scaled thumbnail with a solid accent border.
//    Click opens a QFileDialog; selecting an image fires
//    inputImageSelected(path).
//
// 2. Dialog bar: an inline prompt input. Single-line for now (QLineEdit
//    styled to look like .dbar). Pass 8 wires textChanged to update
//    stage 0's StageConfig.prompt. The contextual hint from the v3
//    mockup ("image loaded → + offers I2I / I2V / I2→3D") is deferred
//    to Pass 7d.3, which is when the kind-picker actually exists.
//
// 3. Add-stage button: 104px-min-width pill button with a large "+"
//    and small "add stage" caption beneath. Click emits
//    addStageRequested — the same signal the rail's add button emits.
//    Pass 7d.3 will wire BOTH this and the rail's button to the same
//    kind-picker QMenu.
//
// Pass 7d.2 emits NO mutation back to the page beyond the upload and
// add-stage signals. Prompt text edits live on the widget only;
// harvesting happens at regenerate time (Pass 8).
//
// Bound to the chain's entry state (sourceImagePath, entryKind) via
// setChain(). The upload box reflects whether an image is loaded; the
// prompt text reflects stage 0's config.prompt if present.

#include "chain/ChainModel.h"

#include <QPoint>
#include <QString>
#include <QWidget>

class QFrame;
class QLabel;
class QLineEdit;
class QPushButton;

namespace spellvision::chain
{

class ChainDialogBarWidget : public QWidget
{
    Q_OBJECT

public:
    explicit ChainDialogBarWidget(QWidget *parent = nullptr);

    // Bind to source chain. Refreshes upload state from
    // chain.sourceImagePath + chain.entryKind, and the prompt input
    // from stage 0's config.prompt (if any stage exists).
    void setChain(const Chain &chain);

    // Pass 8 will set this based on engine.canAddStage(). For 7d.2 the
    // button is always enabled to allow visual review.
    void setCanAddStage(bool canAdd);

signals:
    // Fired when the user picks an image via the upload box. Path is
    // the absolute filesystem path. Pass 8 will wire to
    // engine.setEntryImage(path).
    void inputImageSelected(QString path);

    // Fired when the user clears the upload box (e.g., right-click
    // "Clear"). Pass 7d.2 doesn't implement a clear gesture yet —
    // reserved for Pass 10 polish.
    void inputImageCleared();

    // Fired when the + button is clicked. Same signal shape as
    // ChainRailWidget::addStageRequested. The page connects both
    // sources to the same handler; in Pass 7d.3 that handler shows
    // the kind-picker menu.
    // --- CHAIN STUDIO PASS 7D3 RECOVERY ---
    void addStageRequested(QPoint globalPos);

    // Fired on prompt text change. Pass 8 will wire to update stage 0
    // config.prompt.
    void promptChanged(QString text);

protected:
    // Routes click events on uploadBox_ (a QFrame, which has no
    // clicked signal) to onUploadBoxClicked().
    bool eventFilter(QObject *watched, QEvent *event) override;

private slots:
    void onUploadBoxClicked();
    void onAddStageClicked();

private:
    void refresh();
    void applyUploadEmptyVisual();
    void applyUploadLoadedVisual(const QString &thumbPath);

    Chain   chain_;
    bool    canAddStage_ = true;

    QFrame  *uploadBox_      = nullptr;
    QLabel  *uploadGlyph_    = nullptr;
    QLabel  *uploadCaption_  = nullptr;
    QLabel  *uploadThumb_    = nullptr;   // pixmap version when has image

    QLineEdit  *promptEdit_  = nullptr;
    QPushButton *addButton_  = nullptr;
};

} // namespace spellvision::chain
