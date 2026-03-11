#pragma once

#include <QMainWindow>

class QListWidget;
class QListWidgetItem;
class QTextEdit;
class QLabel;
class QSpinBox;
class QPushButton;
class QDockWidget;
class QAction;
class QLineEdit;
class QDoubleSpinBox;
class QGraphicsView;
class QGraphicsScene;
class QCloseEvent;
class QToolButton;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override = default;

protected:
    void closeEvent(QCloseEvent *event) override;

private slots:
    void createDummyJob();
    void generateTextToImage();
    void browseOutputPath();
    void showAbout();
    void refreshHistory();
    void onHistoryItemClicked(QListWidgetItem *item);
    void openSelectedImage();
    void openSelectedImageFolder();

private:
    void buildMenuBar();
    void buildToolBar();
    void buildStatusBar();
    void buildCentralView();
    void buildDocks();
    void buildInspectorUi();
    void loadWorkspaceState();
    void saveWorkspaceState();
    void logMessage(const QString &message);
    void refreshRustStatus(bool logSummary = false);
    void showGeneratedImage(const QString &imagePath);
    QString pythonExecutable() const;
    QString outputsRoot() const;
    QString imagesRoot() const;
    QString metadataRoot() const;
    QString defaultOutputPath() const;
    QString metadataPathForImage(const QString &imagePath) const;
    void ensureOutputDirs() const;
    void loadMetadataForImage(const QString &imagePath);
    void selectHistoryItemByPath(const QString &imagePath);

    QWidget *centralPanel = nullptr;

    QListWidget *modelList = nullptr;
    QWidget *inspectorWidget = nullptr;
    QTextEdit *logPanel = nullptr;
    QListWidget *historyList = nullptr;
    QTextEdit *metadataPanel = nullptr;

    QLabel *dashboardTitle = nullptr;
    QLabel *rustInfoLabel = nullptr;
    QLabel *queueInfoLabel = nullptr;
    QSpinBox *jobCountSpin = nullptr;
    QPushButton *createJobButton = nullptr;

    QLineEdit *promptEdit = nullptr;
    QLineEdit *negativePromptEdit = nullptr;
    QLineEdit *modelPathEdit = nullptr;
    QSpinBox *widthSpin = nullptr;
    QSpinBox *heightSpin = nullptr;
    QSpinBox *stepsSpin = nullptr;
    QDoubleSpinBox *cfgSpin = nullptr;
    QSpinBox *seedSpin = nullptr;
    QLineEdit *outputPathEdit = nullptr;
    QPushButton *browseOutputButton = nullptr;
    QPushButton *generateButton = nullptr;

    QLabel *imagePathLabel = nullptr;
    QGraphicsView *imageView = nullptr;
    QGraphicsScene *imageScene = nullptr;
    QPushButton *refreshHistoryButton = nullptr;
    QPushButton *openImageButton = nullptr;
    QPushButton *openFolderButton = nullptr;

    QDockWidget *modelsDock = nullptr;
    QDockWidget *inspectorDock = nullptr;
    QDockWidget *logsDock = nullptr;
    QDockWidget *historyDock = nullptr;
    QDockWidget *metadataDock = nullptr;

    QAction *actionNewJob = nullptr;
    QAction *actionGenerateT2I = nullptr;
    QAction *actionRefreshHistory = nullptr;
    QAction *actionOpenImage = nullptr;
    QAction *actionOpenFolder = nullptr;
    QAction *actionExit = nullptr;
    QAction *actionAbout = nullptr;

    QString currentImagePath;
};