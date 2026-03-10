#pragma once

#include <QMainWindow>

class QListWidget;
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
    void refreshRustStatus();
    void showGeneratedImage(const QString &imagePath);
    QString pythonExecutable() const;
    QString defaultOutputPath() const;

    QWidget *centralPanel = nullptr;

    QListWidget *modelList = nullptr;
    QWidget *inspectorWidget = nullptr;
    QTextEdit *logPanel = nullptr;
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

    QDockWidget *modelsDock = nullptr;
    QDockWidget *inspectorDock = nullptr;
    QDockWidget *logsDock = nullptr;

    QAction *actionNewJob = nullptr;
    QAction *actionGenerateT2I = nullptr;
    QAction *actionExit = nullptr;
    QAction *actionAbout = nullptr;
};