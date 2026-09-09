#include "workflows/WorkflowDownloadDialog.h"

#include "ThemeManager.h"

#include <QDialogButtonBox>
#include <QFrame>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QPushButton>
#include <QVBoxLayout>

WorkflowDownloadDialog::WorkflowDownloadDialog(const QStringList &missingNodeClasses,
                                               const QStringList &missingModels,
                                               bool askCivitaiKey,
                                               bool askHfToken,
                                               QWidget *parent)
    : QDialog(parent)
{
    setWindowTitle(tr("Download missing"));
    setModal(true);
    setMinimumWidth(480);

    ThemeManager &theme = ThemeManager::instance();

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section),
                              theme.spacing(ThemeManager::Spacing::Section));
    outer->setSpacing(theme.spacing(ThemeManager::Spacing::Card));

    auto *heading = new QLabel(
        tr("This workflow needs node packs and/or models that are not on this machine."),
        this);
    heading->setObjectName(QStringLiteral("WorkflowDownloadHeading"));
    heading->setWordWrap(true);
    outer->addWidget(heading);

    auto *promise = new QLabel(
        tr("Nothing is downloaded until you click Download."), this);
    promise->setObjectName(QStringLiteral("WorkflowDownloadPromise"));
    promise->setWordWrap(true);
    outer->addWidget(promise);

    auto *list = new QListWidget(this);
    list->setObjectName(QStringLiteral("WorkflowDownloadList"));
    list->setFrameShape(QFrame::NoFrame);
    for (const QString &name : missingNodeClasses)
    {
        if (!name.trimmed().isEmpty())
            list->addItem(tr("Node: %1").arg(name.trimmed()));
    }
    for (const QString &name : missingModels)
    {
        if (!name.trimmed().isEmpty())
            list->addItem(tr("Model: %1").arg(name.trimmed()));
    }
    outer->addWidget(list, 1);

    if (askCivitaiKey)
    {
        auto *link = new QLabel(
            tr("<a href=\"https://civitai.com/user/account\">Create a Civitai API key</a>"),
            this);
        link->setObjectName(QStringLiteral("WorkflowDownloadCivitaiLink"));
        link->setOpenExternalLinks(true);
        link->setTextInteractionFlags(Qt::TextBrowserInteraction);
        outer->addWidget(link);
        civitaiKeyEdit_ = new QLineEdit(this);
        civitaiKeyEdit_->setObjectName(QStringLiteral("WorkflowDownloadCivitaiKey"));
        civitaiKeyEdit_->setEchoMode(QLineEdit::Password);
        civitaiKeyEdit_->setPlaceholderText(tr("Civitai API key"));
        outer->addWidget(civitaiKeyEdit_);
    }

    if (askHfToken)
    {
        auto *link = new QLabel(
            tr("<a href=\"https://huggingface.co/settings/tokens\">Create a Hugging Face token</a>"),
            this);
        link->setObjectName(QStringLiteral("WorkflowDownloadHfLink"));
        link->setOpenExternalLinks(true);
        link->setTextInteractionFlags(Qt::TextBrowserInteraction);
        outer->addWidget(link);
        hfTokenEdit_ = new QLineEdit(this);
        hfTokenEdit_->setObjectName(QStringLiteral("WorkflowDownloadHfToken"));
        hfTokenEdit_->setEchoMode(QLineEdit::Password);
        hfTokenEdit_->setPlaceholderText(tr("Hugging Face token"));
        outer->addWidget(hfTokenEdit_);
    }

    auto *buttons = new QDialogButtonBox(this);
    QPushButton *download = buttons->addButton(tr("Download"), QDialogButtonBox::AcceptRole);
    buttons->addButton(tr("Not now"), QDialogButtonBox::RejectRole);
    download->setDefault(true);
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    outer->addWidget(buttons);
}

QString WorkflowDownloadDialog::typedCivitaiKey() const
{
    return civitaiKeyEdit_ ? civitaiKeyEdit_->text().trimmed() : QString();
}

QString WorkflowDownloadDialog::typedHfToken() const
{
    return hfTokenEdit_ ? hfTokenEdit_->text().trimmed() : QString();
}
