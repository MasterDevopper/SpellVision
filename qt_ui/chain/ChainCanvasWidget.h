#pragma once

// SpellVision — Chain Studio canvas (Pass 7c).
//
// The dominant region of ChainStudioPage. Shows the selected stage's
// selected variation as full media (image only for Pass 7c; video
// rendering deferred to Pass 7d or 8 to avoid mixing the QMediaPlayer
// complexity into this pass). Beneath the media: a pager row with
// prev/next controls, a "variation N of M" indicator, and an inline
// "Lock variation" pill button.
//
// Per the v3 mockup:
//   [image — 84% of canvas height, square aspect ratio]
//   [pager: <  variation N of M  >    Lock pill]
//
// Pass 7c populates the canvas against the same STUB Chain data the
// rail uses. Real engine wiring in Pass 8.
//
// The widget reads from spellvision::chain::Stage / Variation; like
// the rail, it does not touch the engine, store, or watcher. Selection
// signals come INTO the widget via setSelectedStageId(); navigation
// signals come OUT via signals the page connects to engine calls.
//
// Empty state: when a stage has no variations yet (Draft), the canvas
// shows a single placeholder line ("No variations yet — click Regenerate
// to start") instead of an image. Pager controls hide; Lock disables.

#include "chain/ChainModel.h"

#include <QString>
#include <QWidget>

class QFrame;
class QHBoxLayout;
class QLabel;
class QPushButton;
class QResizeEvent;
class QShowEvent;
class QVBoxLayout;

namespace spellvision::chain
{

class ChainCanvasWidget : public QWidget
{
    Q_OBJECT

public:
    explicit ChainCanvasWidget(QWidget *parent = nullptr);

    void setChain(const Chain &chain);
    void setSelectedStageId(const QString &stageId);

signals:
    void variationSelectionChanged(QString stageId, int newVarIdx);
    void lockRequested(QString stageId);

protected:
    // --- PASS 7C RESCALE ON SHOW ---
    // First refresh runs from the constructor before the layout has
    // computed real geometry, so the pixmap scales to a tiny area.
    // Override showEvent to re-refresh once the widget is actually
    // sized, and resizeEvent to rescale on window resize. Both
    // delegate to refresh() which is idempotent and cheap.
    void showEvent(QShowEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

private slots:
    void onPrevClicked();
    void onNextClicked();
    void onLockClicked();

private:
    void refresh();
    const Stage *currentStage() const;
    int currentVariationIdx() const;
    void renderImage(const QString &path);
    void setEmptyState(bool empty);

    Chain  chain_;
    QString selectedStageId_;

    QFrame      *imageHolder_  = nullptr;
    QLabel      *imageLabel_   = nullptr;
    QLabel      *emptyLabel_   = nullptr;
    QPushButton *prevButton_   = nullptr;
    QLabel      *pagerLabel_   = nullptr;
    QPushButton *nextButton_   = nullptr;
    QPushButton *lockButton_   = nullptr;
    QHBoxLayout *pagerRow_     = nullptr;
};

} // namespace spellvision::chain
