#pragma once

// W5 Task 3 — the Models page's inspector.
//
// What the details card showed before: a text block, ONE example image, the trigger words from
// the import sidecar, and a truncated description. What `<stem>.spellvision.json` has carried the
// whole time: up to six pictures with the prompt and settings each was rendered at, the site's
// description, the creator, the licence, and a per-field `recommended` block with a PROVENANCE on
// every value. None of it was read.
//
// Three properties this widget owns.
//
// **Provenance is not optional.** "10 steps, agreed by 10 of this model's own example images" and
// "10 steps, because the family table says so" are different claims. The owner's house checkpoint
// publishes 10 steps unanimously while the family table says 52, and the app rendered it at 52 for
// months — a number with no source invites the user to trust the wrong one.
//
// **The user's own picture.** `model_intel_set_user` copies a chosen image beside the weight and
// marks it in the sidecar so no refresh disturbs it. W1's containment check means the request has
// to carry the model roots, and a picture outside them is REFUSED by design — so this widget
// surfaces the refusal rather than leaving the cover unchanged with no explanation.
//
// **No socket.** The panel builds requests and consumes replies; it never opens a connection. The
// page forwards `workerRequested` and hands answers back through `applyWorkerReply`, which is what
// lets the whole surface be driven by a test with no worker, no ComfyUI and no network.

#include "ModelIntelSidecar.h"

#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QLabel;
class QPushButton;

namespace spellvision::widgets
{
class ElidingLabel;
}

namespace spellvision::assets
{

class ModelInspectorPanel : public QWidget
{
    Q_OBJECT

public:
    explicit ModelInspectorPanel(QWidget *parent = nullptr);

    // The roots the worker will bound this request by. Without them `model_intel_set_user`
    // performs no location check at all — which the worker documents honestly, and which is a gap
    // this caller is responsible for closing rather than inheriting.
    void setModelRoots(const QStringList &roots);

    // `weightPath` is the file on disk; `fileName` is what the page shows when the sidecar has no
    // display name. Passing an empty path clears the panel.
    void showModel(const QString &weightPath, const QString &fileName);
    void clear();

    // --- what the panel is currently showing (the QA / test surface) ---
    QString weightPath() const { return weightPath_; }
    const ModelIntel &intel() const { return intel_; }
    int galleryCount() const;
    QString galleryImageAt(int index) const;
    QString coverPath() const;
    QString headlineText() const;
    QString descriptionText() const;
    QString licenceText() const;
    // The licence sentence, free of the panel, so a test can put a ModelIntel in front of it
    // without laying a sidecar on disk. `licenceText()` is this, applied to the shown model.
    static QString licenceTextFor(const ModelIntel &intel);
    QStringList triggerWords() const;
    // One line per recommended field, each ending in where the number came from.
    QStringList recommendedLines() const;
    QStringList provenanceCaptions() const;
    QString statusText() const;
    bool canOpenOnSite() const;

    // The flow behind "Use my picture…", without the file dialog. The dialog only chooses the
    // path; everything a test needs to exercise begins here.
    void requestUserPicture(const QString &picturePath);
    void requestRefresh();

    // W5 Task 4: the refresh is a long background job with a job id, progress and a cancel, and
    // exactly one thing owns that conversation (`ModelRefreshController`). The panel ASKS and then
    // shows what it is told -- it does not build the request and it does not write its own ending,
    // because a second author for the same status line is how "Metadata refreshed." ends up
    // painted over a summary that said three files could not be looked up.
    void setRefreshStatus(const QString &text, bool isError);
    void setRefreshBusy(bool busy);

public slots:
    // A reply to something this panel asked for. Routed by `type`; anything else is ignored, so a
    // page that forwards every worker reply is not a bug.
    void applyWorkerReply(const QJsonObject &reply);

signals:
    // One request, ready to send. The page owns the socket.
    void workerRequested(const QJsonObject &request);
    // "Apply to this mode" — the resolved settings, for the cockpit.
    void applyRecommendedRequested(const QString &weightPath, const QJsonObject &settings);
    // "Refresh metadata" for THIS weight. The page routes it to the one controller that owns
    // refreshes, so the per-model and the library action cannot disagree about the wire.
    void refreshRequested(const QString &weightPath);

private:
    void rebuild();
    void reloadFromDisk();
    void setStatus(const QString &text, bool isError);
    QJsonObject recommendedAsJson() const;

    QString weightPath_;
    QString fileName_;
    QStringList modelRoots_;
    ModelIntel intel_;
    bool descriptionExpanded_ = false;
    // Driven by the page from the refresh controller; rebuild() must not enable the button back
    // underneath a running job.
    bool refreshBusy_ = false;

    QLabel *headlineLabel_ = nullptr;
    QLabel *subtitleLabel_ = nullptr;
    QWidget *galleryRow_ = nullptr;
    QVector<QLabel *> galleryTiles_;
    QLabel *descriptionLabel_ = nullptr;
    QPushButton *descriptionToggle_ = nullptr;
    QLabel *triggersLabel_ = nullptr;
    QPushButton *copyTriggersButton_ = nullptr;
    QLabel *licenceLabel_ = nullptr;
    QLabel *recommendedLabel_ = nullptr;
    spellvision::widgets::ElidingLabel *statusLabel_ = nullptr;
    QPushButton *applyButton_ = nullptr;
    QPushButton *usePictureButton_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
    QPushButton *openSiteButton_ = nullptr;
};

} // namespace spellvision::assets
