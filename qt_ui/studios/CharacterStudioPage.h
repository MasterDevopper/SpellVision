#pragma once

// Character Studio — Path B: concept plates → character pack → JSON create contract.
// Body mesh is whatever the user selected (characterStudio/bodyGlb). Stages 2–4 stay hidden.

#include "studios/ConceptReferencePacks.h"

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
class QProcess;
class QProgressBar;
class QPushButton;
class QResizeEvent;
class QSplitter;
class QStackedWidget;
class QTextEdit;
class QToolButton;
class DashboardGlassPanel;

namespace spellvision::studios
{

class CharacterStudioPage : public QWidget
{
    Q_OBJECT

public:
    explicit CharacterStudioPage(QWidget *parent = nullptr);

    void setBusy(bool busy, const QString &message = QString());
    void setPreviewImage(const QString &path, const QString &caption = QString());
    void setProjectRoot(const QString &root);
    void updateDisclosure(bool advanced);
    // Ingest a multi-view-ready concept from Concept Reference Lab.
    void acceptConceptReference(const QString &imagePath, const QString &prompt = QString());

signals:
    // Navigate to another shell mode (e.g. "t2i", "i2i", "models").
    void navigateRequested(const QString &modeId);
    // Submit a generation job through MainWindow's worker pipeline.
    void generateRequested(const QString &modeId, const QJsonObject &payload, bool enqueueOnly);
    void openModelsRequested();
    void openWorkflowsRequested();

private:
    enum class StageId
    {
        Concept = 0,
        MultiView,
        BaseMesh,
        Refine,
        GameReady,
        Garments,
        Compose,
        Hair,
        Export,
        Count
    };

    enum class StageStatus
    {
        Locked,
        Ready,
        Running,
        Done,
        Warning,
        Blocked
    };

    struct StageDef
    {
        StageId id = StageId::Concept;
        QString key;
        QString title;
        QString subtitle;
        QString detail;
        StageStatus status = StageStatus::Locked;
        QString artifactPath;
        QString note;
    };

    void buildUi();
    void applyTheme();
    QWidget *buildHeroStrip();
    QWidget *buildStageRail();
    QWidget *buildWorkspace();
    QWidget *buildActionRow();
    QWidget *buildStagePage(StageId id);
    void reflowForWidth(int width);
    void selectStage(int index);
    void refreshStageRail();
    void refreshWorkspace();
    void refreshActionRow();
    void refreshStatusBanner();
    void recomputeStageStatuses();
    void runCurrentStage();
    void lockConcept();
    void openConceptInT2I();
    void generateConcept();
    void completeLookFromPresent();
    QString lookCompleteSourcePath() const;
    void generateMultiViewPrompts();
    void buildJarvisPack();
    void browseJarvisPackImage(QLineEdit *target, const QString &slotTitle);
    void refreshJarvisPackReadiness();
    void createFullCharacter();
    void writeCreateContract(const QString &packDir);
    void runMeshPipeline(StageId id);
    void exportCharacterPackage();
    void browseReferenceImage();
    void browseArtifactForStage();
    void saveProjectState();
    void loadProjectState();
    QString projectsDir() const;
    QString currentProjectDir() const;
    QJsonObject buildConceptPayload() const;
    ConceptContentMode currentContentMode() const;
    void pickModel();
    void pickLora();
    void clearLora();
    void pickHouseLora();
    void clearHouseLora();
    void refreshHouseLoraLabel();
    void refreshModelStackLabels();
    void relayoutConceptPreview();
    QString stageStatusLabel(StageStatus s) const;
    QString stageStatusCss(StageStatus s) const;
    void setStageNote(StageId id, const QString &note);
    void probeExternalTools();

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    QString projectRoot_;
    QString projectName_ = QStringLiteral("character_01");
    bool advanced_ = false;
    bool busy_ = false;
    int currentStage_ = 0;
    QVector<StageDef> stages_;

    // Tool probes (SpellBound / pixal3d-spike).
    bool hasPixalEnv_ = false;
    bool hasBlender_ = false;
    bool hasUltraShape_ = false;
    QString pixalPython_;
    QString blenderPath_;
    QString spikeRoot_;

    // Chrome
    QSplitter *mainSplit_ = nullptr;
    QWidget *stageRail_ = nullptr;
    DashboardGlassPanel *heroPanel_ = nullptr;
    QLabel *heroTitle_ = nullptr;
    QLabel *heroSubtitle_ = nullptr;
    QLabel *heroMeta_ = nullptr;
    QLabel *statusBanner_ = nullptr;
    QProgressBar *progress_ = nullptr;

    QListWidget *stageList_ = nullptr;
    QStackedWidget *stageStack_ = nullptr;

    // Concept controls
    QLineEdit *characterNameEdit_ = nullptr;
    QTextEdit *conceptPromptEdit_ = nullptr;
    QTextEdit *negativePromptEdit_ = nullptr;
    QComboBox *stylePresetCombo_ = nullptr;
    QComboBox *poseCombo_ = nullptr;
    QComboBox *aspectCombo_ = nullptr;
    QComboBox *contentModeCombo_ = nullptr;
    QLineEdit *referencePathEdit_ = nullptr;
    QLabel *conceptPreview_ = nullptr;
    QLabel *conceptPreviewCaption_ = nullptr;
    QPushButton *completeLookBtn_ = nullptr;
    QCheckBox *seedLockCheck_ = nullptr;
    QLineEdit *seedEdit_ = nullptr;
    QCheckBox *houseStyleLoraCheck_ = nullptr;
    QLabel *houseLoraPathLabel_ = nullptr;
    QPushButton *pickHouseLoraBtn_ = nullptr;
    QPushButton *clearHouseLoraBtn_ = nullptr;
    QString houseLoraPath_;
    QString houseLoraDisplay_;
    QDoubleSpinBox *refDenoiseSpin_ = nullptr;

    // Model stack (required on-page — never silent T2I merge-only)
    QLabel *modelValueLabel_ = nullptr;
    QLabel *licenseNoteLabel_ = nullptr;
    QLabel *loraValueLabel_ = nullptr;
    QPushButton *pickModelBtn_ = nullptr;
    QPushButton *pickLoraBtn_ = nullptr;
    QPushButton *clearLoraBtn_ = nullptr;
    QString selectedModelPath_;
    QString selectedModelDisplay_;
    QString selectedLoraPath_;
    QString selectedLoraDisplay_;

    // Multi-view
    QComboBox *viewCountCombo_ = nullptr;
    QLabel *multiViewSummary_ = nullptr;
    QLineEdit *packFaceFrontEdit_ = nullptr;
    QLineEdit *packFace3qEdit_ = nullptr;
    QLineEdit *packClothesFrontEdit_ = nullptr;
    QLineEdit *packClothesSideEdit_ = nullptr;
    QLineEdit *packClothesBackEdit_ = nullptr;
    QLineEdit *packClothes3qEdit_ = nullptr;
    QLineEdit *packPiecesEdit_ = nullptr;
    QLineEdit *packPaletteEdit_ = nullptr;
    QLabel *jarvisPackReadinessLabel_ = nullptr;
    QPushButton *buildJarvisPackBtn_ = nullptr;
    QProcess *jarvisPackProcess_ = nullptr;

    // Mesh / pipeline
    QComboBox *meshBackendCombo_ = nullptr;
    QComboBox *detailTargetCombo_ = nullptr;
    QCheckBox *runUltraShapeCheck_ = nullptr;
    QCheckBox *generateLodsCheck_ = nullptr;
    QCheckBox *bakeMapsCheck_ = nullptr;
    QLabel *meshToolStatus_ = nullptr;
    QLabel *meshArtifactLabel_ = nullptr;

    // Garments
    QTextEdit *garmentListEdit_ = nullptr;
    QComboBox *garmentRegimeCombo_ = nullptr;
    QString lastClothesOnlyDest_;

    // Export
    QComboBox *exportFormatCombo_ = nullptr;
    QCheckBox *writeLicenseSidecarCheck_ = nullptr;
    QLabel *exportSummary_ = nullptr;

    // Actions
    QPushButton *primaryActionBtn_ = nullptr;
    QPushButton *secondaryActionBtn_ = nullptr;
    QPushButton *openT2IBtn_ = nullptr;
    QPushButton *saveProjectBtn_ = nullptr;
    QLabel *actionHint_ = nullptr;

    // Advanced-only widgets (revealed in place)
    QWidget *advancedConceptBlock_ = nullptr;
    QWidget *advancedMeshBlock_ = nullptr;
};

} // namespace spellvision::studios
