#pragma once

#include <QDialog>
#include <QString>

class QCheckBox;
class QLineEdit;
class QListWidget;
class QPushButton;
class QTextEdit;

class WorkflowImportDialog : public QDialog
{
    Q_OBJECT

public:
    explicit WorkflowImportDialog(const QString &projectRoot,
                                  const QString &pythonExecutable,
                                  QWidget *parent = nullptr);

signals:
    void profilesChanged();

private slots:
    void browseWorkflowSource();
    void importWorkflow();
    void refreshProfiles();
    void onProfileSelectionChanged();
    void openSelectedProfileFolder();

private:
    QString sendWorkerRequest(const QString &jsonPayload);
    void appendLog(const QString &text);
    void renderImportResult(const QString &jsonText);
    void renderProfilesResult(const QString &jsonText);

    QString m_projectRoot;
    QString m_pythonExecutable;

    QLineEdit *sourcePathEdit = nullptr;
    QLineEdit *profileNameEdit = nullptr;
    QCheckBox *autoInstallNodesCheck = nullptr;
    QCheckBox *autoInstallModelsCheck = nullptr;
    QPushButton *browseButton = nullptr;
    QPushButton *importButton = nullptr;
    QPushButton *refreshProfilesButton = nullptr;
    QPushButton *openFolderButton = nullptr;
    QListWidget *profilesList = nullptr;
    QTextEdit *detailsPanel = nullptr;
    QTextEdit *logPanel = nullptr;
};
