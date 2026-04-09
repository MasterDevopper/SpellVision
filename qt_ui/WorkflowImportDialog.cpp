#include "WorkflowImportDialog.h"

#include <QCheckBox>
#include <QDialogButtonBox>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QVBoxLayout>

namespace
{
QString defaultImportedWorkflowsRoot()
{
    return QStringLiteral("runtime/imported_workflows");
}
}

WorkflowImportDialog::WorkflowImportDialog(QWidget *parent)
    : QDialog(parent)
{
    setObjectName(QStringLiteral("WorkflowImportDialog"));
    setWindowTitle(QStringLiteral("Import Workflow"));
    setModal(true);
    resize(720, 420);

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(18, 18, 18, 18);
    root->setSpacing(12);

    auto *title = new QLabel(QStringLiteral("Import a Comfy-style workflow"), this);
    title->setStyleSheet(QStringLiteral("font-size: 18px; font-weight: 800; color: #f2f6fc;"));
    root->addWidget(title);

    auto *subtitle = new QLabel(
        QStringLiteral("Pass 1 supports JSON, PNG, and WebP workflow sources. The worker will scan the workflow, infer task/media type, create a profile, and optionally apply dependency actions."),
        this);
    subtitle->setWordWrap(true);
    subtitle->setStyleSheet(QStringLiteral("font-size: 12px; color: #9fb0ca;"));
    root->addWidget(subtitle);

    auto *form = new QFormLayout;
    form->setFieldGrowthPolicy(QFormLayout::ExpandingFieldsGrow);
    form->setLabelAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    form->setHorizontalSpacing(12);
    form->setVerticalSpacing(10);

    auto *sourceRow = new QHBoxLayout;
    sourceRow->setSpacing(8);
    sourceEdit_ = new QLineEdit(this);
    sourceEdit_->setPlaceholderText(QStringLiteral("Choose a workflow source (.json, .png, .webp)"));
    auto *sourceBrowseButton = new QPushButton(QStringLiteral("Browse"), this);
    connect(sourceBrowseButton, &QPushButton::clicked, this, &WorkflowImportDialog::browseForSource);
    sourceRow->addWidget(sourceEdit_, 1);
    sourceRow->addWidget(sourceBrowseButton);
    form->addRow(QStringLiteral("Source"), sourceRow);

    profileNameEdit_ = new QLineEdit(this);
    profileNameEdit_->setPlaceholderText(QStringLiteral("Optional display/profile name"));
    form->addRow(QStringLiteral("Profile Name"), profileNameEdit_);

    comfyRootEdit_ = new QLineEdit(this);
    comfyRootEdit_->setPlaceholderText(QStringLiteral("Managed Comfy root"));
    form->addRow(QStringLiteral("Comfy Root"), comfyRootEdit_);

    auto *destinationRow = new QHBoxLayout;
    destinationRow->setSpacing(8);
    destinationRootEdit_ = new QLineEdit(this);
    destinationRootEdit_->setPlaceholderText(QStringLiteral("Import library root"));
    destinationRootEdit_->setText(defaultImportedWorkflowsRoot());
    auto *destinationBrowseButton = new QPushButton(QStringLiteral("Browse"), this);
    connect(destinationBrowseButton, &QPushButton::clicked, this, &WorkflowImportDialog::browseForDestinationRoot);
    destinationRow->addWidget(destinationRootEdit_, 1);
    destinationRow->addWidget(destinationBrowseButton);
    form->addRow(QStringLiteral("Library Root"), destinationRow);

    autoApplyNodeDepsCheck_ = new QCheckBox(QStringLiteral("Auto-apply node dependencies"), this);
    autoApplyModelDepsCheck_ = new QCheckBox(QStringLiteral("Auto-apply model dependencies"), this);
    form->addRow(QString(), autoApplyNodeDepsCheck_);
    form->addRow(QString(), autoApplyModelDepsCheck_);

    root->addLayout(form);

    supportHintEdit_ = new QPlainTextEdit(this);
    supportHintEdit_->setReadOnly(true);
    supportHintEdit_->setMaximumHeight(120);
    supportHintEdit_->setPlainText(
        QStringLiteral("Supported source kinds\n"
                       "• JSON file\n"
                       "• PNG with embedded workflow metadata\n"
                       "• WebP with embedded workflow metadata\n\n"
                       "Import result will include\n"
                       "• inferred task command\n"
                       "• inferred media type\n"
                       "• saved workflow/profile paths\n"
                       "• warnings / errors / dependency health"));
    root->addWidget(supportHintEdit_);

    validationLabel_ = new QLabel(this);
    validationLabel_->setWordWrap(true);
    validationLabel_->setStyleSheet(QStringLiteral("font-size: 11px; color: #d9b36c;"));
    root->addWidget(validationLabel_);

    buttonBox_ = new QDialogButtonBox(QDialogButtonBox::Cancel, this);
    importButton_ = new QPushButton(QStringLiteral("Scan && Import"), this);
    importButton_->setDefault(true);
    buttonBox_->addButton(importButton_, QDialogButtonBox::AcceptRole);
    connect(buttonBox_, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(importButton_, &QPushButton::clicked, this, &QDialog::accept);
    root->addWidget(buttonBox_);

    connect(sourceEdit_, &QLineEdit::textChanged, this, &WorkflowImportDialog::updateValidationState);
    connect(profileNameEdit_, &QLineEdit::textChanged, this, &WorkflowImportDialog::updateValidationState);
    connect(comfyRootEdit_, &QLineEdit::textChanged, this, &WorkflowImportDialog::updateValidationState);
    connect(destinationRootEdit_, &QLineEdit::textChanged, this, &WorkflowImportDialog::updateValidationState);

    updateValidationState();
}

void WorkflowImportDialog::setManagedComfyRoot(const QString &path)
{
    comfyRootEdit_->setText(path.trimmed());
    updateValidationState();
}

void WorkflowImportDialog::setDefaultDestinationRoot(const QString &path)
{
    if (!path.trimmed().isEmpty())
        destinationRootEdit_->setText(path.trimmed());
    updateValidationState();
}

QString WorkflowImportDialog::sourcePath() const
{
    return sourceEdit_ ? sourceEdit_->text().trimmed() : QString();
}

QString WorkflowImportDialog::profileName() const
{
    return profileNameEdit_ ? profileNameEdit_->text().trimmed() : QString();
}

QString WorkflowImportDialog::comfyRoot() const
{
    return comfyRootEdit_ ? comfyRootEdit_->text().trimmed() : QString();
}

QString WorkflowImportDialog::destinationRoot() const
{
    return destinationRootEdit_ ? destinationRootEdit_->text().trimmed() : QString();
}

bool WorkflowImportDialog::autoApplyNodeDeps() const
{
    return autoApplyNodeDepsCheck_ && autoApplyNodeDepsCheck_->isChecked();
}

bool WorkflowImportDialog::autoApplyModelDeps() const
{
    return autoApplyModelDepsCheck_ && autoApplyModelDepsCheck_->isChecked();
}

void WorkflowImportDialog::browseForSource()
{
    const QString filePath = QFileDialog::getOpenFileName(
        this,
        QStringLiteral("Choose workflow source"),
        sourcePath(),
        QStringLiteral("Workflow Sources (*.json *.png *.webp);;JSON (*.json);;Images (*.png *.webp);;All Files (*.*)"));
    if (!filePath.isEmpty())
        sourceEdit_->setText(filePath);
}

void WorkflowImportDialog::browseForDestinationRoot()
{
    const QString dirPath = QFileDialog::getExistingDirectory(
        this,
        QStringLiteral("Choose workflow library root"),
        destinationRoot());
    if (!dirPath.isEmpty())
        destinationRootEdit_->setText(dirPath);
}

void WorkflowImportDialog::updateValidationState()
{
    const QString source = sourcePath();
    QString message;
    bool ok = true;

    if (source.isEmpty())
    {
        ok = false;
        message = QStringLiteral("Choose a workflow source to continue.");
    }
    else
    {
        const QFileInfo info(source);
        const QString suffix = info.suffix().trimmed().toLower();
        if (!info.exists())
        {
            ok = false;
            message = QStringLiteral("The selected workflow source does not exist.");
        }
        else if (suffix != QStringLiteral("json") && suffix != QStringLiteral("png") && suffix != QStringLiteral("webp"))
        {
            ok = false;
            message = QStringLiteral("Pass 1 only supports .json, .png, and .webp workflow sources.");
        }
        else if (destinationRoot().isEmpty())
        {
            ok = false;
            message = QStringLiteral("Choose an import library root.");
        }
        else
        {
            message = QStringLiteral("Ready to import. The worker will scan the workflow and create a profile.");
        }
    }

    if (validationLabel_)
        validationLabel_->setText(message);
    if (importButton_)
        importButton_->setEnabled(ok);
}
