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

    QString filePath() const { return filePath_; }

private:
    void load();
    void save() const;

    QString filePath_;
    QHash<QString, ModelOverlay> overlays_;
};

} // namespace spellvision::assets
