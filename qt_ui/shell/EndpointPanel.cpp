#include "shell/EndpointPanel.h"

#include <QCheckBox>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QSettings>
#include <QTableWidget>
#include <QVBoxLayout>

#include "ThemeManager.h"
#include "style/SvKit.h"

namespace spellvision::shell
{
namespace
{
const char *const kConsentKey = "runtime/allowRemoteQueuing";

int token(ThemeManager::Spacing spacing)
{
    return ThemeManager::instance().spacing(spacing);
}
} // namespace

EndpointPanel::EndpointPanel(QWidget *parent)
    : QWidget(parent)
    , registry_(EndpointRegistry::defaults(QString()))
    , statusResolver_([](const QString &id) { return EndpointProbe::instance().statusFor(id); })
{
    buildUi();
}

void EndpointPanel::buildUi()
{
    setObjectName(QStringLiteral("EndpointPanel"));
    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(0, 0, 0, 0);
    outer->setSpacing(token(ThemeManager::Spacing::Tight));

    table_ = new QTableWidget(0, ColumnCount, this);
    table_->setObjectName(QStringLiteral("EndpointTable"));
    table_->setHorizontalHeaderLabels({QStringLiteral("Machine"), QStringLiteral("Address"),
                                       QStringLiteral("Status"), QStringLiteral("ComfyUI"),
                                       QStringLiteral("GPU / VRAM"), QStringLiteral("Checkpoints"),
                                       QStringLiteral("Proven families")});
    table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    table_->setSelectionMode(QAbstractItemView::SingleSelection);
    table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table_->verticalHeader()->setVisible(false);
    table_->horizontalHeader()->setStretchLastSection(true);
    outer->addWidget(table_);

    auto *actions = new QHBoxLayout();
    actions->setContentsMargins(0, 0, 0, 0);
    actions->setSpacing(token(ThemeManager::Spacing::Tight));
    addButton_ = new QPushButton(QStringLiteral("Add machine…"), this);
    editButton_ = new QPushButton(QStringLiteral("Rename…"), this);
    removeButton_ = new QPushButton(QStringLiteral("Remove"), this);
    refreshButton_ = new QPushButton(QStringLiteral("Check now"), this);
    for (QPushButton *button : {addButton_, editButton_, removeButton_, refreshButton_})
    {
        kit::setRole(button, style::Role::Secondary);
        actions->addWidget(button);
    }
    actions->addStretch(1);
    outer->addLayout(actions);

    // ONE consent, and it governs the only thing that needs consenting to: sending a prompt, and the
    // input image with it, to another machine on the network. The share-folder consent it replaces
    // guarded a QSettings value with no consumer anywhere in the tree.
    remoteConsentCheck_ = new QCheckBox(QStringLiteral("Allow queuing to remote workers"), this);
    remoteConsentCheck_->setObjectName(QStringLiteral("EndpointRemoteConsent"));
    remoteConsentCheck_->setToolTip(QStringLiteral(
        "Off by default. When off, every job runs on this machine whatever a page is set to.\n\n"
        "Queuing to another machine sends it the prompt and any input image over the local network, "
        "unencrypted and unauthenticated -- ComfyUI has no auth."));
    outer->addWidget(remoteConsentCheck_);

    familyCaption_ = new QLabel(QStringLiteral("Proven families for the selected machine"), this);
    outer->addWidget(familyCaption_);
    familyList_ = new QListWidget(this);
    familyList_->setObjectName(QStringLiteral("EndpointFamilyList"));
    familyList_->setMaximumHeight(140);
    outer->addWidget(familyList_);

    honestyLabel_ = new QLabel(this);
    honestyLabel_->setWordWrap(true);
    honestyLabel_->setText(QStringLiteral(
        "Whole jobs only. VRAM does not add (does not pool VRAM): 32 GB and 24 GB are two machines, "
        "not 56. Generate will not queue to an offline worker, and a family is ticked here only "
        "after a render has really finished on that machine."));
    outer->addWidget(honestyLabel_);

    connect(table_, &QTableWidget::itemSelectionChanged, this, [this]() { rebuildFamilyList(); });
    connect(familyList_, &QListWidget::itemChanged, this, &EndpointPanel::onFamilyItemChanged);
    connect(refreshButton_, &QPushButton::clicked, this, &EndpointPanel::refreshRequested);
    connect(removeButton_, &QPushButton::clicked, this, [this]() { removeSelected(); });
    connect(addButton_, &QPushButton::clicked, this, [this]() {
        bool ok = false;
        const QString url = QInputDialog::getText(
            this, QStringLiteral("Add a machine"),
            QStringLiteral("ComfyUI address (host:port):"), QLineEdit::Normal, QString(), &ok);
        if (!ok || url.trimmed().isEmpty())
            return;
        const QString label = QInputDialog::getText(
            this, QStringLiteral("Add a machine"), QStringLiteral("Name:"), QLineEdit::Normal,
            QString(), &ok);
        if (!ok)
            return;
        addEndpoint(label, url);
    });
    connect(editButton_, &QPushButton::clicked, this, [this]() {
        bool ok = false;
        const QString label = QInputDialog::getText(
            this, QStringLiteral("Rename"), QStringLiteral("Name:"), QLineEdit::Normal,
            selectedEndpointId(), &ok);
        if (ok)
            renameSelected(label);
    });
    connect(remoteConsentCheck_, &QCheckBox::toggled, this, [this](bool on) {
        QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
        settings.setValue(QString::fromLatin1(kConsentKey), on);
    });

    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const QSignalBlocker blocker(remoteConsentCheck_);
    remoteConsentCheck_->setChecked(settings.value(QString::fromLatin1(kConsentKey), false).toBool());
}

void EndpointPanel::setStatusResolver(std::function<EndpointStatus(const QString &)> resolver)
{
    if (resolver)
        statusResolver_ = std::move(resolver);
    refreshRows();
}

void EndpointPanel::setRegistry(const EndpointRegistry &registry)
{
    registry_ = registry;
    refreshRows();
}

bool EndpointPanel::removeSelected()
{
    lastRefusal_.clear();
    const QString id = selectedEndpointId();
    if (id.isEmpty())
    {
        lastRefusal_ = QStringLiteral("Nothing is selected.");
        return false;
    }
    if (!registry_.remove(id, &lastRefusal_))
        return false;
    registry_.save();
    refreshRows();
    emit registryChanged();
    return true;
}

bool EndpointPanel::addEndpoint(const QString &label, const QString &url)
{
    lastRefusal_.clear();
    Endpoint endpoint;
    endpoint.label = label.trimmed();
    endpoint.baseUrl = url;
    if (!registry_.upsert(endpoint, &lastRefusal_))
        return false;
    registry_.save();
    refreshRows();
    emit registryChanged();
    return true;
}

bool EndpointPanel::renameSelected(const QString &label)
{
    lastRefusal_.clear();
    const QString id = selectedEndpointId();
    const Endpoint *existing = registry_.find(id);
    if (!existing)
    {
        lastRefusal_ = QStringLiteral("Nothing is selected.");
        return false;
    }
    Endpoint renamed = *existing;
    renamed.label = label.trimmed();
    if (renamed.label.isEmpty())
    {
        lastRefusal_ = QStringLiteral("A machine needs a name.");
        return false;
    }
    if (!registry_.upsert(renamed, &lastRefusal_))
        return false;
    registry_.save();
    refreshRows();
    emit registryChanged();
    return true;
}

bool EndpointPanel::setSelectedEnabled(bool enabled)
{
    lastRefusal_.clear();
    if (!registry_.setEnabled(selectedEndpointId(), enabled))
    {
        lastRefusal_ = QStringLiteral("Nothing is selected.");
        return false;
    }
    registry_.save();
    refreshRows();
    emit registryChanged();
    return true;
}

void EndpointPanel::onFamilyItemChanged(QListWidgetItem *item)
{
    if (applyingFamilies_ || !item)
        return;
    setFamilyChecked(item->text(), item->checkState() == Qt::Checked);
}

bool EndpointPanel::setFamilyChecked(const QString &family, bool checked)
{
    lastRefusal_.clear();
    const QString id = selectedEndpointId();
    if (id.isEmpty())
    {
        lastRefusal_ = QStringLiteral("Nothing is selected.");
        rebuildFamilyList();
        return false;
    }
    if (checked)
    {
        lastRefusal_ = QStringLiteral(
            "A family is ticked by a render finishing on that machine, not here.");
        rebuildFamilyList();
        return false;
    }
    const bool changed = registry_.disallowFamily(id, family);
    if (changed)
    {
        registry_.save();
        refreshRows();
        emit registryChanged();
    }
    else
    {
        lastRefusal_ = QStringLiteral("That family was not ticked.");
        rebuildFamilyList();
    }
    return changed;
}

bool EndpointPanel::recordGateRender(const QString &endpointId, const QString &family)
{
    if (!registry_.allowFamily(endpointId, family))
        return false;
    registry_.save();
    refreshRows();
    emit registryChanged();
    return true;
}

bool EndpointPanel::remoteQueuingAllowed() const
{
    return remoteConsentCheck_ && remoteConsentCheck_->isChecked();
}

void EndpointPanel::setRemoteQueuingAllowed(bool allowed)
{
    if (remoteConsentCheck_)
        remoteConsentCheck_->setChecked(allowed);
}

} // namespace spellvision::shell
