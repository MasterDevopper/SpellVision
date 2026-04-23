#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QMainWindow>
#include <QMap>
#include <QString>
#include <QStackedWidget>

class CommandPaletteDialog;
class CustomTitleBar;
class HomePage;
class ImageGenerationPage;
class ManagerPage;
class ModePage;
class ModelManagerPage;
class QueueManager;
class QueueTableModel;
class QueueFilterProxyModel;
class SettingsPage;
class WorkflowLibraryPage;

class QAbstractButton;
class QEvent;
class QDockWidget;
class QFrame;
class QLabel;
class QPushButton;
class QLineEdit;
class QProgressBar;
class QComboBox;
class QTableView;
class QTextEdit;
class QTabWidget;
class QToolButton;
class QSplitter;
class QTimer;
class QWidget;
class QProcess;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override = default;

protected:
    void changeEvent(QEvent *event) override;
    bool nativeEvent(const QByteArray &eventType, void *message, qintptr *result) override;

private slots:
    void switchToMode(const QString &modeId);
    void openManager(const QString &managerId);
    void syncBottomTelemetry();
    void onQueueChanged();

private:
    void buildShell();
    void buildPages();
    void buildPersistentDocks();
    void buildBottomTelemetryBar();
    void connectGenerationPage(ImageGenerationPage *page, const QString &modeId);
    void handleHomeLaunchRequest(const QString &modeId,
                                 const QString &title,
                                 const QString &subtitle,
                                 const QString &sourceLabel);
    ImageGenerationPage *generationPageForMode(const QString &modeId) const;
    void submitGenerationRequest(ImageGenerationPage *page, const QString &modeId, const QJsonObject &payload, bool enqueueOnly);
    void pollWorkerQueueStatus();
    QJsonObject sendWorkerRequest(const QJsonObject &request, QString *stderrText = nullptr, bool *startedOk = nullptr) const;
    QString workerTaskCommandForMode(const QString &modeId) const;
    QString resolveProjectRoot() const;
    QString resolvePythonExecutable() const;
    QJsonObject buildWorkerGenerationRequest(const QString &modeId, const QJsonObject &payload) const;
    QJsonObject buildWorkflowLaunchRequest(const QJsonObject &profile) const;
    void launchWorkflowProfile(const QJsonObject &profile);
    void applyWorkerQueueResponse(const QJsonObject &response);
    void syncGenerationPreviewsFromQueue();
    void appendLogLine(const QString &text);

    QWidget *createSideRail();
    QWidget *createBottomUtilityWidget();
    QWidget *createQueueWidget();
    QWidget *createDetailsWidget();
    QWidget *createLogsWidget();

    void hideNativeDockTitleBar(QDockWidget *dock);
    void updateDockChrome();
    void applyQueueDockChrome();
    void applyBottomUtilityTrayChrome();
    bool hasActiveQueueWork() const;
    bool isCompactShellWidth() const;
    bool isGenerationWorkspaceMode() const;
    int preferredBottomUtilityExpandedHeight(bool compact) const;

    void showTitleBarMenu(const QString &menuId, const QPoint &globalPos);
    void showLayoutMenu(const QPoint &globalPos);
    void showSystemMenu(const QPoint &globalPos);
    void showCommandPalette();
    void triggerCommand(const QString &command);
    void openWorkflowImportDialog();
    void togglePrimarySidebar();
    void toggleBottomPanels();
    void toggleDetailsPanel();

    void applyShellStateForMode(const QString &modeId);
    void setBottomPageContext(const QString &text);
    QString pageContextForMode(const QString &modeId) const;

    void updateModeButtonState(const QString &modeId);
    void updateActiveQueueStrip();
    void refreshDetailsPanel();
    void updateDetailsPanelForModeContext();
    void updateDetailsPanelForQueueSelection();
    void showWorkflowImportResult(const QJsonObject &response, const QString &stderrText);
    void openWorkflowDraft(const QJsonObject &draft);

    void configureDetailsActions(const QString &primaryId,
                                 const QString &primaryText,
                                 const QString &secondaryId,
                                 const QString &secondaryText,
                                 const QString &tertiaryId,
                                 const QString &tertiaryText);
    void triggerDetailsAction(const QString &actionId);
    QString selectedQueueId() const;

    CustomTitleBar *titleBar_ = nullptr;
    QWidget *centralShell_ = nullptr;
    QWidget *sideRail_ = nullptr;
    QStackedWidget *pageStack_ = nullptr;

    HomePage *homePage_ = nullptr;
    WorkflowLibraryPage *workflowsPage_ = nullptr;
    ModePage *historyPage_ = nullptr;
    ModePage *inspirationPage_ = nullptr;
    ModelManagerPage *modelsPage_ = nullptr;
    ManagerPage *managersPage_ = nullptr;
    SettingsPage *settingsPage_ = nullptr;

    ImageGenerationPage *t2iPage_ = nullptr;
    ImageGenerationPage *i2iPage_ = nullptr;
    ImageGenerationPage *t2vPage_ = nullptr;
    ImageGenerationPage *i2vPage_ = nullptr;

    QueueManager *queueManager_ = nullptr;
    QueueTableModel *queueTableModel_ = nullptr;
    QueueFilterProxyModel *queueFilterProxyModel_ = nullptr;
    QTableView *queueTableView_ = nullptr;
    QLineEdit *queueSearchEdit_ = nullptr;
    QComboBox *queueStateFilter_ = nullptr;
    QWidget *queueExpandedContent_ = nullptr;
    QWidget *bottomUtilityHeaderBar_ = nullptr;
    QLabel *queueDockStateLabel_ = nullptr;
    QToolButton *queueExpandButton_ = nullptr;
    QToolButton *bottomQueueButton_ = nullptr;
    QToolButton *bottomDetailsButton_ = nullptr;
    QToolButton *bottomLogsButton_ = nullptr;
    bool queueDockUserExpanded_ = false;
    bool bottomUtilityUserExpanded_ = false;

    QDockWidget *detailsDock_ = nullptr;
    QDockWidget *queueDock_ = nullptr;
    QDockWidget *logsDock_ = nullptr;
    QTabWidget *bottomUtilityTabs_ = nullptr;
    QSplitter *bottomUtilitySplitter_ = nullptr;
    QProcess *workflowImportProcess_ = nullptr;
    bool detailsDockPinnedOpen_ = false;

    QLabel *activeQueueTitleLabel_ = nullptr;
    QLabel *activeQueueSummaryLabel_ = nullptr;
    QLabel *detailsTitleLabel_ = nullptr;
    QLabel *detailsBodyLabel_ = nullptr;
    QLabel *detailsContextValueLabel_ = nullptr;
    QLabel *detailsSelectionValueLabel_ = nullptr;
    QLabel *detailsQueueValueLabel_ = nullptr;
    QLabel *detailsStatusValueLabel_ = nullptr;
    QPushButton *detailsPrimaryActionButton_ = nullptr;
    QPushButton *detailsSecondaryActionButton_ = nullptr;
    QPushButton *detailsTertiaryActionButton_ = nullptr;
    QString detailsPrimaryActionId_;
    QString detailsSecondaryActionId_;
    QString detailsTertiaryActionId_;
    QTextEdit *logsView_ = nullptr;

    QLabel *bottomReadyLabel_ = nullptr;
    QLabel *bottomPageLabel_ = nullptr;
    QLabel *bottomRuntimeLabel_ = nullptr;
    QLabel *bottomQueueLabel_ = nullptr;
    QLabel *bottomVramLabel_ = nullptr;
    QLabel *bottomModelLabel_ = nullptr;
    QLabel *bottomLoraLabel_ = nullptr;
    QLabel *bottomStateLabel_ = nullptr;
    QProgressBar *bottomProgressBar_ = nullptr;

    CommandPaletteDialog *commandPaletteDialog_ = nullptr;
    QMap<QString, QAbstractButton *> modeButtons_;
    QMap<QString, QWidget *> modePages_;
    QString currentModeId_ = QStringLiteral("home");
    QTimer *workerQueuePollTimer_ = nullptr;
};