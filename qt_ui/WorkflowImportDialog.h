#pragma once

#include <QDialog>

class QCheckBox;
class QDialogButtonBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QPlainTextEdit;

class WorkflowImportDialog final : public QDialog
{
    Q_OBJECT

public:
    explicit WorkflowImportDialog(QWidget *parent = nullptr);

    void setManagedComfyRoot(const QString &path);
    void setDefaultDestinationRoot(const QString &path);

    QString sourcePath() const;
    QString profileName() const;
    QString comfyRoot() const;
    QString destinationRoot() const;
    bool autoApplyNodeDeps() const;
    bool autoApplyModelDeps() const;

private slots:
    void browseForSource();
    void browseForDestinationRoot();
    void updateValidationState();

private:
    QLineEdit *sourceEdit_ = nullptr;
    QLineEdit *profileNameEdit_ = nullptr;
    QLineEdit *comfyRootEdit_ = nullptr;
    QLineEdit *destinationRootEdit_ = nullptr;
    QCheckBox *autoApplyNodeDepsCheck_ = nullptr;
    QCheckBox *autoApplyModelDepsCheck_ = nullptr;
    QLabel *validationLabel_ = nullptr;
    QPlainTextEdit *supportHintEdit_ = nullptr;
    QPushButton *importButton_ = nullptr;
    QDialogButtonBox *buttonBox_ = nullptr;
};
