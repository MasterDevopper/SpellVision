#include "ModelKindTabs.h"

#include "../ThemeManager.h"
#include "../style/SvKit.h"
#include "../style/SvStyle.h"

#include <QDir>
#include <QHBoxLayout>
#include <QPushButton>

namespace spellvision::assets
{

namespace
{
using spellvision::kit::setRole;

// The vocabulary, in tab order. `python/model_intelligence/kinds.py` is the other copy, and the
// two are held together by `tests/cpp/test_model_kind_tabs.cpp` reading the real sidecars the
// Python side wrote.
struct KindRow
{
    const char *kind;
    const char *tabLabel;  // plural, on the chip
    const char *oneLabel;  // singular, on the list row and the card badge
};

const KindRow kKinds[] = {
    {"checkpoint",      "Checkpoints",      "Checkpoint"},
    {"diffusion_model", "Diffusion models", "Diffusion model"},
    {"lora",            "LoRAs",            "LoRA"},
    {"vae",             "VAE",              "VAE"},
    {"text_encoder",    "Text encoders",    "Text encoder"},
    {"clip_vision",     "Vision",           "Vision encoder"},
    {"embedding",       "Embeddings",       "Embedding"},
    {"upscaler",        "Upscalers",        "Upscaler"},
    {"controlnet",      "ControlNet",       "ControlNet"},
    {"style_model",     "Style models",     "Style model"},
};

const QString &allId()
{
    static const QString id = QStringLiteral("all");
    return id;
}

const QString &otherId()
{
    static const QString id = QStringLiteral("other");
    return id;
}

// The FOLDER a ComfyUI library files a kind under, matched as a whole path SEGMENT.
//
// Matching a substring against the whole path is the mechanism this task exists to remove, and it
// is wrong in both directions: `.../loras/krea2DepthControlnet_v10.safetensors` contains
// "controlnet" and `.../checkpoints/sd3/...` contains "sd3". A directory name is a statement
// somebody made about the file; a word inside a file name is not.
struct FolderRule
{
    const char *folder;
    const char *kind;
};

const FolderRule kFolderRules[] = {
    {"checkpoints", "checkpoint"},
    {"diffusion_models", "diffusion_model"},
    {"unet", "diffusion_model"},
    {"loras", "lora"},
    {"lora", "lora"},
    {"vae", "vae"},
    {"text_encoders", "text_encoder"},
    {"text_encoder", "text_encoder"},
    {"clip", "text_encoder"},
    {"clip_vision", "clip_vision"},
    {"embeddings", "embedding"},
    {"upscale_models", "upscaler"},
    {"controlnet", "controlnet"},
    {"controlnets", "controlnet"},
    {"style_models", "style_model"},
};
} // namespace

namespace ModelKindTabs
{

QString normaliseKind(const QString &raw)
{
    const QString token = raw.trimmed().toLower();
    for (const KindRow &row : kKinds)
    {
        if (token == QLatin1String(row.kind))
            return QString::fromLatin1(row.kind);
    }
    // `video_stack`, `unknown`, "", a hand-edited word, a kind a newer build invented: all of them
    // are Other. Nothing here promotes an unrecognised token to a real tab.
    return otherId();
}

QString normaliseFamily(const QString &raw)
{
    const QString text = raw.trimmed();
    const QString token = text.toLower();
    if (token.isEmpty() || token == QStringLiteral("unknown") || token == QStringLiteral("none")
        || token == QStringLiteral("null"))
    {
        return QString();
    }
    return text;
}

QString kindFromPath(const QString &path)
{
    // Native separators first: the page hands this Windows paths.
    const QString normalized = QDir::fromNativeSeparators(path).toLower();
    const QStringList segments = normalized.split(QLatin1Char('/'), Qt::SkipEmptyParts);
    // Deepest directory first, and the file name itself is not a directory -- `loras/x.safetensors`
    // is a LoRA even when the file is called `...Controlnet...`.
    for (int index = segments.size() - 2; index >= 0; --index)
    {
        for (const FolderRule &rule : kFolderRules)
        {
            if (segments.at(index) == QLatin1String(rule.folder))
                return QString::fromLatin1(rule.kind);
        }
    }
    // Nothing said what this is. Other, and visible -- not a guess off the file name, which is the
    // mechanism that put a LoRA under ControlNet.
    return otherId();
}

QString kindLabel(const QString &kind)
{
    const QString normalised = normaliseKind(kind);
    for (const KindRow &row : kKinds)
    {
        if (normalised == QLatin1String(row.kind))
            return QString::fromLatin1(row.oneLabel);
    }
    return QStringLiteral("Other");
}

const QVector<ModelKindTab> &tabs()
{
    static const QVector<ModelKindTab> all = []() {
        QVector<ModelKindTab> out;
        out.push_back({allId(), QStringLiteral("All")});
        for (const KindRow &row : kKinds)
            out.push_back({QString::fromLatin1(row.kind), QString::fromLatin1(row.tabLabel)});
        out.push_back({otherId(), QStringLiteral("Other")});
        return out;
    }();
    return all;
}

QString allTabId() { return allId(); }
QString otherTabId() { return otherId(); }

bool tabAccepts(const QString &tabId, const QString &kind)
{
    const QString tab = tabId.trimmed().toLower();
    if (tab.isEmpty() || tab == allId())
        return true;
    return normaliseKind(kind) == tab;
}

QHash<QString, int> counts(const QStringList &kinds)
{
    QHash<QString, int> out;
    for (const ModelKindTab &tab : tabs())
        out.insert(tab.id, 0);
    for (const QString &raw : kinds)
    {
        ++out[normaliseKind(raw)];
        ++out[allId()];
    }
    return out;
}

QString labelWithCount(const QString &tabId, int count)
{
    for (const ModelKindTab &tab : tabs())
    {
        if (tab.id == tabId)
            return QStringLiteral("%1 %2").arg(tab.label).arg(count);
    }
    return QStringLiteral("%1 %2").arg(tabId).arg(count);
}

} // namespace ModelKindTabs

ModelKindTabBar::ModelKindTabBar(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("ModelKindTabBar"));

    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(0, 0, 0, 0);
    row->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Hairline));

    for (const ModelKindTab &tab : ModelKindTabs::tabs())
    {
        auto *button = new QPushButton(tab.label, this);
        button->setObjectName(QStringLiteral("ModelKindTab"));
        button->setProperty("tabId", tab.id);
        button->setCheckable(true);
        button->setCursor(Qt::PointingHandCursor);
        setRole(button, spellvision::style::Role::Tab);
        connect(button, &QPushButton::clicked, this, [this, id = tab.id]() { selectTab(id, true); });
        buttons_.insert(tab.id, button);
        row->addWidget(button);
    }
    row->addStretch(1);

    currentTabId_ = ModelKindTabs::allTabId();
    buttons_.value(currentTabId_)->setChecked(true);
    setCounts({});
}

void ModelKindTabBar::setCounts(const QHash<QString, int> &counts)
{
    counts_ = counts;
    for (const ModelKindTab &tab : ModelKindTabs::tabs())
    {
        QPushButton *button = buttons_.value(tab.id);
        if (!button)
            continue;
        const int count = counts.value(tab.id, 0);
        button->setText(ModelKindTabs::labelWithCount(tab.id, count));
        // All and Other stay whatever the count is. Every other tab earns its place by holding
        // something: eleven chips on a library with five kinds in it is a bar the user reads past.
        const bool always = (tab.id == ModelKindTabs::allTabId() || tab.id == ModelKindTabs::otherTabId());
        button->setVisible(always || count > 0);
    }

    // The tab the user was on may have just emptied (a refresh that lost a drive). Fall back to
    // All rather than leaving the grid filtered by a chip that is no longer on screen.
    QPushButton *current = buttons_.value(currentTabId_);
    if (!current || !current->isVisibleTo(this))
        selectTab(ModelKindTabs::allTabId(), true);
}

void ModelKindTabBar::setCurrentTabId(const QString &tabId)
{
    selectTab(tabId, false);
}

void ModelKindTabBar::selectTab(const QString &tabId, bool emitSignal)
{
    const QString next = buttons_.contains(tabId) ? tabId : ModelKindTabs::allTabId();
    for (auto it = buttons_.cbegin(); it != buttons_.cend(); ++it)
        it.value()->setChecked(it.key() == next);
    if (next == currentTabId_)
        return;
    currentTabId_ = next;
    if (emitSignal)
        emit tabChanged(currentTabId_);
}

QStringList ModelKindTabBar::visibleTabIds() const
{
    QStringList out;
    for (const ModelKindTab &tab : ModelKindTabs::tabs())
    {
        const QPushButton *button = buttons_.value(tab.id);
        if (button && button->isVisibleTo(const_cast<ModelKindTabBar *>(this)))
            out << tab.id;
    }
    return out;
}

QString ModelKindTabBar::labelForTab(const QString &tabId) const
{
    const QPushButton *button = buttons_.value(tabId);
    return button ? button->text() : QString();
}

} // namespace spellvision::assets
