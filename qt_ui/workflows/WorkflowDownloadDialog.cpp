#include "workflows/WorkflowDownloadDialog.h"

#include "ThemeManager.h"

#include <QDialogButtonBox>
#include <QFrame>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QVBoxLayout>

WorkflowDownloadDialog::WorkflowDownloadDialog(const QStringList &missingNodeClasses,
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
        tr("This workflow needs %n node class(es) that are not installed.",
           nullptr,
           missingNodeClasses.size()),
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
            list->addItem(name.trimmed());
    }
    outer->addWidget(list, 1);

    auto *buttons = new QDialogButtonBox(this);
    QPushButton *download = buttons->addButton(tr("Download"), QDialogButtonBox::AcceptRole);
    buttons->addButton(tr("Not now"), QDialogButtonBox::RejectRole);
    download->setDefault(true);
    connect(buttons, &QDialogButtonBox::accepted, this, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    outer->addWidget(buttons);
}
