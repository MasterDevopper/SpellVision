#pragma once

// Comic Studio — panel-grid comic page composer.
// Builds multi-panel pages from script + style, generates each panel via the
// existing T2I path, and composites a page preview for export.

#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QPainter;

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
    // The bottom telemetry bar reads the model of the page you are LOOKING AT (shell/TelemetryPresenter);
    // without this it could only see the generation pages and fell back to the last-run model.
    QString selectedModelValue() const { return selectedModelPath_; }
    QString selectedModelDisplayName() const { return selectedModelDisplay_; }

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
    // Speech balloon (with tail) for dialogue, narration box for caption. Comic lettering, not
    // subtitles; the caption used to reach the manifest and never the page.
    void drawPanelLettering(QPainter &painter, const QRect &panel, const QString &dialogue, const QString &caption);
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
    // The classifier's verdict for the picked checkpoint, captured at pick time. The licence badge
    // and the generate warn are keyed on it; the payload this page sends carries `model` but used to
    // carry no family at all, so the warn fell back to a substring test on the model PATH.
    QString selectedModelFamily_;
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
