#pragma once

#include <QByteArray>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QMainWindow>
#include <QMap>
#include <QString>
#include <QStringList>
#include <QStackedWidget>

class CommandPaletteDialog;
class CustomTitleBar;
class GlowProgressBar;
class HomePage;
// --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
namespace spellvision::chain { class ChainStudioPage; }
class ImageGenerationPage;
class ModePage;
class ModelManagerPage;
class QueueManager;
class QueueTableModel;
class QueueFilterProxyModel;
class SettingsPage;
class T2VHistoryPage;
class WorkflowLibraryPage;

namespace spellvision::workers
{
class WorkerQueueController;
}

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
class QNetworkAccessManager;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override = default;

    // --- CHAIN STUDIO PASS 8C.1: public API for chain submission ---
    // ChainStudioPage uses these two methods to (a) bind its
    // ChainCompletionWatcher to the live QueueManager and (b) submit
    // engine-built payloads through the same worker pipeline that
    // ImageGenerationPage uses, without needing a page pointer.

    // Returns the QueueManager owned by this MainWindow. May be
    // nullptr if called before buildPersistentDocks() has run; safe
    // for ChainStudioPage to read once during its own construction
    // (which happens after MainWindow::buildPages -> after queue
    // manager exists).
    QueueManager *queueManager() const { return queueManager_; }

    // Submit a chain engine payload through the worker pipeline.
    // modeId is the lowercase task string ("t2i" / "i2i" / "t2v" /
    // "i2v"); queueItemId is the engine-generated UUID that the
    // ChainCompletionWatcher will look for on returned queue items.
    // Returns true if the worker accepted the request; false on any
    // validation rejection, missing-model, missing-input-image, or
    // worker transport error. (Engine treats false as a rejection
    // and rolls back the pending variation.)
    bool submitChainGenerationRequest(const QString &modeId,
                                      const QJsonObject &payload,
                                      const QString &queueItemId);

    // Phase 6: app-global Simple/Advanced disclosure mode. The title-bar toggle drives it; it is
    // persisted. Phase 7 consumers read isAdvancedMode() / subscribe to disclosureModeChanged().
    bool isAdvancedMode() const { return advancedMode_; }

signals:
    void disclosureModeChanged(bool advanced);

protected:
    void changeEvent(QEvent *event) override;
    bool nativeEvent(const QByteArray &eventType, void *message, qintptr *result) override;

private slots:
    void setDisclosureMode(bool advanced); // Phase 6: apply + persist + broadcast the global mode
    void switchToMode(const QString &modeId);
    void openManager(const QString &managerId);
    // Send-to-generation router (doc 22 §3): dispatch a Models-page card action by type + family,
    // and auto-populate the model/LoRA's trigger words into the prompt.
    void sendModelToGeneration(const QString &value, const QString &family, const QString &type,
                               const QStringList &triggerWords);
    void syncBottomTelemetry();
    void startVramTelemetryPolling();
    void pollVramTelemetry();
    void startComfyHealthPolling();
    void pollComfyHealth();
    void updateBackendHealthLabel();
    void onQueueChanged();

private:
    void buildShell();
    void buildPages();
    void buildPersistentDocks();
    void buildBottomTelemetryBar();
    void buildQueueOverlay();
    void positionQueueOverlay();
    bool eventFilter(QObject *watched, QEvent *event) override;
    void showEvent(QShowEvent *event) override; // starts idle page pre-warm once, after first show
    void connectGenerationPage(ImageGenerationPage *page, const QString &modeId);
    void handleHomeLaunchRequest(const QString &modeId,
                                 const QString &title,
                                 const QString &subtitle,
                                 const QString &sourceLabel);
    ImageGenerationPage *generationPageForMode(const QString &modeId) const;
    // --- LAZY PAGE CONSTRUCTION (startup latency fix) ---
    // The four ImageGenerationPages cost ~6s to construct (intrinsic widget-tree
    // build, GUI-thread-only -- QWidget construction cannot be threaded). Building
    // them eagerly in buildPages() blocked the event loop until ~9.8s, so the window
    // did not paint until then. Instead they are deferred: built on first navigation
    // (on-demand) and, failing that, warmed one-per-event-loop-turn after show()
    // (idle pre-warm). ensureGenerationPageBuilt() is the SINGLE, idempotent
    // construction path both routes call -- so an on-demand page and a pre-warmed
    // page are identical by construction and cannot drift. isGenerationMode() is a
    // pure, side-effect-free predicate for "can this mode host a generation page?"
    // used where callers need existence WITHOUT forcing a build. Startup is now
    // O(1) in page count (fixed eager set); the deferred work is amortized during
    // idle. A new page added later should follow this pattern, not revert to eager.
    bool isGenerationMode(const QString &modeId) const;
    void ensureGenerationPageBuilt(const QString &modeId);
    void startIdlePagePrewarm();
    void scheduleNextPagePrewarm(int delayMs = 0);
    void submitGenerationRequest(ImageGenerationPage *page, const QString &modeId, const QJsonObject &payload, bool enqueueOnly);
    void pollWorkerQueueStatus();
    // Fired on a successful queue poll. On the worker down->up edge only, re-scans
    // built image pages so their displayed families match classifier routing.
    void onWorkerQueueReachable();
    QJsonObject sendWorkerRequest(const QJsonObject &request, QString *stderrText = nullptr, bool *startedOk = nullptr, int timeoutMs = 120000) const;
    // Detection accelerator (option A): batch-classify catalog paths via the worker's
    // one layered classifier so Qt's displayed family matches what the worker routes.
    // Returns path -> family; empty on any failure (worker down) -> scanner keeps its fallback.
    QHash<QString, QString> classifyModelsViaWorker(const QStringList &paths) const;
    // Component Auto-Population (Doc 19 §6 A2): round-trip the selected primary + task + the UI's
    // component file choices to the worker's resolve_component_stack (the A1 engine), returning the
    // per-slot [{component,tier,value,valid_options,required}]. Empty on failure -> combos stay Auto.
    QJsonArray resolveComponentStackViaWorker(const QString &primary, const QString &family,
                                              const QString &task, const QJsonObject &choices) const;
    // Phase 3b: the fast/quality operating-point table for a video family. A STATIC table -- fetched
    // once from the video_family_contracts snapshot and cached, so the cockpit can render its selector
    // with no per-change round-trip. Returns {default_operating_point, operating_points:[...]} ({} on
    // an unknown family / worker down -> the cockpit hides the selector).
    QJsonObject operatingPointsForFamily(const QString &family) const;
    // Fires on EVERY quit path via qApp::aboutToQuit (close button, Alt+F4, menu Quit,
    // QApplication::quit) -- the detached ComfyUI (:8188 + GPU) has no other teardown.
    void tearDownComfyOnExit();
    QString workerTaskCommandForMode(const QString &modeId) const;
    QString resolveProjectRoot() const;
    QString resolvePythonExecutable() const;
    QJsonObject buildWorkerGenerationRequest(const QString &modeId, const QJsonObject &payload) const;
    QJsonObject buildWorkflowLaunchRequest(const QJsonObject &profile,
                                           const QString &modelOverride = QString(),
                                           const QString &loraOverride = QString(),
                                           const QString &loraScaleOverride = QString()) const;
    void launchWorkflowProfile(const QJsonObject &profile);
    // Model Library Arc — Stage 3. The primary launch path: an explicit model override (from the
    // Models page "Use workflow") wins outright; the Flows-page launch passes an empty override and
    // falls back to the dev hook / cockpit selection. hasExplicitModel distinguishes "unbound on
    // purpose" (dual-loader, empty override) from "no override supplied".
    void launchWorkflowProfileWithModel(const QJsonObject &profile, const QString &explicitModel,
                                        bool hasExplicitModel);
    void applyWorkerQueueResponse(const QJsonObject &response);
    void syncGenerationPreviewsFromQueue();
    void appendLogLine(const QString &text);

    QWidget *createSideRail();
    QWidget *createQueueWidget();
    QWidget *createDetailsWidget();
    QWidget *createLogsWidget();

    void hideNativeDockTitleBar(QDockWidget *dock);
    void updateDockChrome();
    void applyQueuePresentationForCurrentMode();
    void applyQueueDockChrome();
    void applyBottomUtilityTrayChrome();
    bool hasActiveQueueWork() const;
    bool isCompactShellWidth() const;
    bool isGenerationWorkspaceMode() const;
    int preferredBottomUtilityExpandedHeight(bool compact) const;

    void showLayoutMenu(const QPoint &globalPos);
    void showSystemMenu(const QPoint &globalPos);
    void showCommandPalette();
    void populatePaletteTopLevel();          // fill the palette with the grouped top-level command set
    void enterModelPickerMode(bool loraOnly); // second-level palette: pick a model / LoRA from inventory
    void cycleTheme();                        // advance to the next ThemeManager preset
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
    // --- CHAIN STUDIO PASS 7C-PRELUDE RAIL ENTRY ---
    spellvision::chain::ChainStudioPage *chainStudioPage_ = nullptr;
    WorkflowLibraryPage *workflowsPage_ = nullptr;
    T2VHistoryPage *historyPage_ = nullptr;
    ModePage *inspirationPage_ = nullptr;
    ModelManagerPage *modelsPage_ = nullptr;
    SettingsPage *settingsPage_ = nullptr;

    ImageGenerationPage *t2iPage_ = nullptr;
    ImageGenerationPage *i2iPage_ = nullptr;
    ImageGenerationPage *t2vPage_ = nullptr;
    ImageGenerationPage *i2vPage_ = nullptr;
    // Deferred generation-page mode ids still awaiting idle pre-warm (drained
    // one-per-turn by scheduleNextPagePrewarm; on-demand builds skip themselves).
    QStringList prewarmQueue_;
    bool prewarmStarted_ = false; // showEvent fires more than once; kick the warm only once

    bool advancedMode_ = false; // Phase 6 global disclosure mode (persisted; Phase 7 consumes)
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
    QDockWidget *queueDock_ = nullptr; // retired in Phase 5; stays nullptr (overlay replaces it)
    QDockWidget *logsDock_ = nullptr;
    QWidget *queueOverlay_ = nullptr;  // frameless slide-up drawer over the page area (Phase 5)
    QToolButton *queueOverlayCloseButton_ = nullptr;
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
    QLabel *bottomBackendLabel_ = nullptr;
    QLabel *bottomQueueLabel_ = nullptr;
    QLabel *bottomVramLabel_ = nullptr;
    QLabel *bottomModelLabel_ = nullptr;
    QLabel *bottomLoraLabel_ = nullptr;
    QLabel *bottomStateLabel_ = nullptr;
    QLabel *bottomEtaLabel_ = nullptr;
    GlowProgressBar *bottomProgressBar_ = nullptr;
    QTimer *vramTelemetryTimer_ = nullptr;
    QString lastVramTelemetryText_ = QStringLiteral("VRAM: checking");

    // Backend health dots. Worker (:8765) reachability is the workerReachable_ latch; Comfy (:8188)
    // is a direct client-side GET /system_stats probe (no worker plumbing) on comfyHealthTimer_.
    QNetworkAccessManager *comfyHealthNam_ = nullptr;
    QTimer *comfyHealthTimer_ = nullptr;
    bool comfyReachable_ = false;
    bool comfyHealthInFlight_ = false;
    bool comfyHealthProbed_ = false; // false until the first probe returns (dot reads "checking")

    CommandPaletteDialog *commandPaletteDialog_ = nullptr;
    // Phase 3b operating-point table cache (lazy, fetched once from video_family_contracts).
    mutable QHash<QString, QJsonObject> operatingPointsByFamily_;
    mutable bool operatingPointsFetched_ = false;
    QMap<QString, QAbstractButton *> modeButtons_;
    QMap<QString, QWidget *> modePages_;
    QMap<QString, QString> lastSyncedGenerationPreviewByMode_;
    QMap<QString, QString> lastSyncedGenerationErrorByMode_;
    QString currentModeId_ = QStringLiteral("home");
    spellvision::workers::WorkerQueueController *workerQueueController_ = nullptr;
    // Latched worker reachability. Re-scan image catalogs only on the false->true
    // edge (worker became ready) so display families upgrade from the startup-race
    // fallback to the classifier verdict -- not on every 1800ms poll.
    bool workerReachable_ = false;
};