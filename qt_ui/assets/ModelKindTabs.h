#pragma once

// W5 Task 1 — the Models page's tabs, and the vocabulary they are built from.
//
// The page used to answer "what kind of weight is this" with `ModelManagerPage::detectType`, six
// names matched as path substrings. It collapsed `clip_vision` and `text_encoders` into one
// "Encoder", gave embeddings no kind at all (they fell through to "Model"), and had no idea what
// a style model was. The worker's classifier has answered this properly for months and writes its
// answer into `<stem>.spellvision.json`; this is the tab layer over that answer.
//
// The rule the whole file exists for: **a weight whose kind nobody could determine goes to
// `other`, and the Other tab is always visible.** A wrong tab is worse than an honest one, and a
// model that appears under no tab at all is worst — the user cannot tell it from a model that is
// not installed. Every path through here therefore ends in a kind from the vocabulary; nothing
// returns an empty string or a guess.
//
// A tab with no models is hidden, so the bar stays readable on the owner's library (five kinds of
// ten are present) — with All and Other exempt, because Other hidden is exactly the disappearance
// the rule forbids, and a zero there is a fact worth showing.

#include <QHash>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QButtonGroup;
class QHBoxLayout;
class QPushButton;

namespace spellvision::assets
{

struct ModelKindTab
{
    QString id;    // "all", a kind from the vocabulary, or "other"
    QString label; // "LoRAs", "Text encoders", …
};

namespace ModelKindTabs
{
// The ten kinds, plus "other". Mirrors `python/model_intelligence/kinds.py::KIND_VOCABULARY`,
// including its mapping of the classifier's `video_stack` / `unknown` onto `other`.
QString normaliseKind(const QString &raw);

// "" when nothing determined a family. The live library still holds sidecars whose family is the
// literal string "unknown", which is truthy and therefore reads as a real family everywhere that
// does not go through here.
QString normaliseFamily(const QString &raw);

// The honest fallback for a weight with NO sidecar: the folder a ComfyUI library puts a kind in.
// It answers in the same vocabulary and returns "other" rather than guessing "checkpoint", so a
// library that has never been through a refresh still files everything somewhere visible.
QString kindFromPath(const QString &path);

// Singular display name for one kind ("LoRA", "Text encoder", …). What the list column and the
// card badge show.
QString kindLabel(const QString &kind);

// Ordered: All first, Other last, the ten kinds in between.
const QVector<ModelKindTab> &tabs();

QString allTabId();
QString otherTabId();

// Does `tabId` show a model of `kind`? "all" accepts everything; every other tab accepts exactly
// its own kind, and an unrecognised kind is normalised first — so nothing can fall between tabs.
bool tabAccepts(const QString &tabId, const QString &kind);

// Per-tab counts for an inventory's kinds, including "all". Every tab id is present, zeros
// included, so a caller never has to distinguish "no entry" from "none of those".
QHash<QString, int> counts(const QStringList &kinds);

QString labelWithCount(const QString &tabId, int count);
} // namespace ModelKindTabs

// The chip row. Counts come from the inventory; a tab with none is hidden except All and Other.
class ModelKindTabBar : public QWidget
{
    Q_OBJECT
public:
    explicit ModelKindTabBar(QWidget *parent = nullptr);

    void setCounts(const QHash<QString, int> &counts);
    QString currentTabId() const { return currentTabId_; }
    void setCurrentTabId(const QString &tabId);

    // The tabs the user can actually see and press right now — what a test asks instead of
    // walking children and re-deriving the visibility rule it is trying to check.
    QStringList visibleTabIds() const;
    QString labelForTab(const QString &tabId) const;

signals:
    void tabChanged(const QString &tabId);

private:
    void selectTab(const QString &tabId, bool emitSignal);

    QHash<QString, QPushButton *> buttons_;
    QHash<QString, int> counts_;
    QString currentTabId_;
};

} // namespace spellvision::assets
