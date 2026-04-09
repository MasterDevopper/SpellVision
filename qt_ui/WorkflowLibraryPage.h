#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QWidget>

class QLabel;
class QListWidget;
class QListWidgetItem;
class QPlainTextEdit;
class QPushButton;
class QProcess;

class WorkflowLibraryPage final : public QWidget
{
    Q_OBJECT

public:
    explicit WorkflowLibraryPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &path);
    void setPythonExecutable(const QString &path);
    void setProfilesRoot(const QString &path);

public slots:
    void refreshProfiles();

signals:
    void importWorkflowRequested();
    void launchWorkflowRequested(const QJsonObject &profile);

private slots:
    void handleSelectionChanged();
    void handleLaunchSelectedWorkflow();
    void handleOpenSelectedFolder();
    void handleOpenSelectedScanReport();
    void handleCopyPaths();

private:
    void buildUi();
    void startRefreshProcess();
    void populateProfiles(const QJsonArray &profiles);
    void renderSelectedProfile();
    QJsonObject currentProfile() const;

    QString projectRoot_;
    QString pythonExecutable_;
    QString profilesRoot_;

    QListWidget *profileList_ = nullptr;

    QLabel *statusLabel_ = nullptr;
    QLabel *detailTitleLabel_ = nullptr;
    QLabel *detailSummaryLabel_ = nullptr;
    QPlainTextEdit *detailTextEdit_ = nullptr;

    QPushButton *refreshButton_ = nullptr;
    QPushButton *importButton_ = nullptr;
    QPushButton *openImportRootButton_ = nullptr;

    QPushButton *launchSelectedButton_ = nullptr;
    QPushButton *openSelectedFolderButton_ = nullptr;
    QPushButton *openSelectedScanReportButton_ = nullptr;
    QPushButton *copyPathsButton_ = nullptr;

    QProcess *refreshProcess_ = nullptr;
    QString selectedProfilePath_;
};