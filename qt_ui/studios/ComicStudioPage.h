#pragma once

// Comic Studio — panel-grid comic page composer.
// Builds multi-panel pages from script + style, generates each panel via the
// existing T2I path, and composites a page preview for export.

#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QFrame;
class QLabel;
class QLineEdit;
class QListWidget;
class QProgressBar;
class QPushButton;
class QResizeEvent;
class QSpinBox;
class QSplitter;
class QStackedWidget;
class QTextEdit;
class DashboardGlassPanel;

namespace spellvision::studios
{

struct ComicPanel
{
    int index = 0;
    QString title;
    QString beat;       // short narrative beat
    QString prompt;     // full generation prompt
    QString dialogue;
    QString caption;
    QString camera;     // wide / medium / close / extreme-close
    QString imagePath;
    bool done = false;
};

class ComicStudioPage : public QWidget
{
    Q_OBJECT

public:
    explicit ComicStudioPage(QWidget *parent = nullptr);

    void setBusy(bool busy, const QString &message = QString());
    void setPanelResult(int panelIndex, const QString &imagePath);
    void setProjectRoot(const QString &root);
    void updateDisclosure(bool advanced);

signals:
    void navigateRequested(const QString &modeId);
    void generateRequested(const QString &modeId, const QJsonObject &payload, bool enqueueOnly);
    void openModelsRequested();

private:
    void buildUi();
    void applyTheme();
    QWidget *buildHero();
    QWidget *buildLeftColumn();
    QWidget *buildCenterCanvas();
    QWidget *buildRightInspector();
    QWidget *buildActionRow();

    void applyLayoutPreset(const QString &presetId);
    void rebuildPanelList();
    void selectPanel(int index);
    void refreshPanelInspector();
    void refreshCanvas();
    void refreshHeroMeta();
    // Simple hides these controls; it does not switch them off. The notice says which of them are
    // still shaping the render, so "why is every panel identical" has an answer on screen.
    void refreshAdvancedOverrideNotice();
    // The aspect preset WRITES the width/height spins rather than competing with them, so one pair
    // of values is the truth in both modes.
    void applyAspectPresetToSize();
    void syncPanelFromInspector();
    void generateSelectedPanel();
    void generateAllPanels();
    void openSelectedInT2I();
    void exportPage();
    void saveProject();
    void loadProject();
    void autoFillPromptsFromScript();
    QJsonObject buildPanelPayload(const ComicPanel &panel) const;
    void pickModel();
    void pickLora();
    void clearLora();
    void refreshModelStackLabels();
    QString projectsDir() const;
    QString styleScaffold() const;
    QString cameraDirective(const QString &camera) const;
    int colsForLayout() const;
    int rowsForLayout() const;
    void reflowForWidth(int width);

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    QString projectRoot_;
    QString projectName_ = QStringLiteral("comic_01");
    bool advanced_ = false;
    bool busy_ = false;
    int selectedPanel_ = 0;
    QString layoutId_ = QStringLiteral("grid_2x2");
    QVector<ComicPanel> panels_;

    QSplitter *mainSplit_ = nullptr;
    QWidget *leftColumn_ = nullptr;
    QWidget *rightColumn_ = nullptr;

    // Hero
    DashboardGlassPanel *heroPanel_ = nullptr;
    QLabel *heroTitle_ = nullptr;
    QLabel *heroSubtitle_ = nullptr;
    QLabel *heroMeta_ = nullptr;
    QLabel *statusBanner_ = nullptr;
    QProgressBar *progress_ = nullptr;

    // Script / style
    QLineEdit *titleEdit_ = nullptr;
    QComboBox *layoutCombo_ = nullptr;
    QComboBox *styleCombo_ = nullptr;
    QComboBox *aspectCombo_ = nullptr;
    QTextEdit *scriptEdit_ = nullptr;
    QTextEdit *globalStyleEdit_ = nullptr;
    QCheckBox *keepCharacterCheck_ = nullptr;
    QLineEdit *characterLockEdit_ = nullptr;
    QSpinBox *panelCountSpin_ = nullptr;

    // Panel list + inspector
    QListWidget *panelList_ = nullptr;
    QLineEdit *panelTitleEdit_ = nullptr;
    QTextEdit *panelBeatEdit_ = nullptr;
    QTextEdit *panelPromptEdit_ = nullptr;
    QTextEdit *panelDialogueEdit_ = nullptr;
    QTextEdit *panelCaptionEdit_ = nullptr;
    QComboBox *panelCameraCombo_ = nullptr;
    QLabel *panelPreview_ = nullptr;
    QLabel *panelStatus_ = nullptr;

    // Canvas grid of panel plates
    QWidget *canvasHost_ = nullptr;
    QVector<QLabel *> canvasCells_;
    QLabel *pagePreviewCaption_ = nullptr;

    // Advanced
    QWidget *advancedBlock_ = nullptr;
    QComboBox *samplerHintCombo_ = nullptr;
    QSpinBox *stepsSpin_ = nullptr;
    QDoubleSpinBox *cfgSpin_ = nullptr;
    QLineEdit *seedEdit_ = nullptr;
    QCheckBox *randomSeedCheck_ = nullptr;
    QSpinBox *widthSpin_ = nullptr;
    QSpinBox *heightSpin_ = nullptr;

    // Model stack (on-page — required for generate)
    QLabel *modelValueLabel_ = nullptr;
    QLabel *loraValueLabel_ = nullptr;
    QPushButton *pickModelBtn_ = nullptr;
    QPushButton *pickLoraBtn_ = nullptr;
    QPushButton *clearLoraBtn_ = nullptr;
    QString selectedModelPath_;
    QString selectedModelDisplay_;
    QString selectedLoraPath_;
    QString selectedLoraDisplay_;

    // Actions
    QPushButton *genPanelBtn_ = nullptr;
    QPushButton *genAllBtn_ = nullptr;
    QPushButton *exportBtn_ = nullptr;
    QPushButton *saveBtn_ = nullptr;
    QPushButton *openT2IBtn_ = nullptr;
    QPushButton *autoScriptBtn_ = nullptr;
    QLabel *actionHint_ = nullptr;
    QLabel *advancedOverrideLabel_ = nullptr;
};

} // namespace spellvision::studios
