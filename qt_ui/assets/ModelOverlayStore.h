#pragma once

// Model Library Arc — S0 data layer (design doc 22, §2.4).
// SpellVision-owned per-model state (favorite / hidden / user tags). Kept in the app's OWN cache,
// keyed on sha256 (survives a model moving directories). CORRECTION #2: this is NEVER written back
// to the metadata sidecar — that's the download manager's file and it would clobber user state.

#include <QHash>
#include <QString>
#include <QStringList>

namespace spellvision::assets
{

struct ModelOverlay
{
    bool favorite = false;
    bool hidden = false;
    QStringList userTags;
    QString lastUsedMode;
    int useCount = 0;
    // Model Library Arc — Stage 2 (workflow<->model association). The imported-workflow slug this
    // model is bound to, set ONLY on explicit user action (never guessed). Stored as the slug rather
    // than an absolute profile path so it survives the imported-workflows root moving -- consistent
    // with this overlay being sha256-keyed to survive the MODEL moving. One workflow per model for
    // now; not designed to preclude a later multi-binding (t2v/i2v/first2last) refinement.
    QString workflowProfile;
};

class ModelOverlayStore
{
public:
    // `filePath` empty -> default location (AppLocalDataLocation/model_overlay.json).
    explicit ModelOverlayStore(const QString &filePath = QString());

    // `key` is a stable identity — prefer sha256, fall back to an abspath hash when absent.
    ModelOverlay overlay(const QString &key) const;
    bool isFavorite(const QString &key) const;
    bool isHidden(const QString &key) const;

    void setFavorite(const QString &key, bool favorite);
    void setHidden(const QString &key, bool hidden);
    void setUserTags(const QString &key, const QStringList &tags);
    void noteUsed(const QString &key, const QString &mode); // bumps useCount + lastUsedMode

    QString workflowProfile(const QString &key) const;      // "" when no workflow is bound
    void setWorkflowProfile(const QString &key, const QString &profile); // "" clears the binding

    QString filePath() const { return filePath_; }

private:
    void load();
    void save() const;

    QString filePath_;
    QHash<QString, ModelOverlay> overlays_;
};

} // namespace spellvision::assets
