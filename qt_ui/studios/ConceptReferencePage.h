#pragma once

// Concept Reference Lab — multi-view-ready concept art presets.
// Asset-type buttons (body / clothing / building / prop) + SFW/NSFW content mode
// inject positive/negative scaffolds that multi-view and mesh pipelines adhere to.
// Includes local model + LoRA pickers so generation does not require visiting T2I first.

#include "studios/ConceptReferencePacks.h"

#include <QJsonObject>
#include <QString>
#include <QWidget>

class QButtonGroup;
class QComboBox;
class QFrame;
class QLabel;
class QCheckBox;
class QLineEdit;
class QProgressBar;
class QPushButton;
class QResizeEvent;
class QSplitter;
class QTextEdit;
class QToolButton;
class DashboardGlassPanel;

namespace spellvision::studios
{

class ConceptReferencePage : public QWidget
{
    Q_OBJECT

public:
    explicit ConceptReferencePage(QWidget *parent = nullptr);

    void setBusy(bool busy, const QString &message = QString());
    void setPreviewImage(const QString &path, const QString &caption = QString());
    void setProjectRoot(const QString &root);
    void updateDisclosure(bool advanced);

signals:
    void navigateRequested(const QString &modeId);
    void generateRequested(const QString &modeId, const QJsonObject &payload, bool enqueueOnly);
    void openModelsRequested();
    void sendToCharacterStudioRequested(const QString &imagePath, const QString &prompt);

protected:
    void resizeEvent(QResizeEvent *event) override;
    void showEvent(QShowEvent *event) override;

private:
    void buildUi();
    void applyTheme();
    void reflowForWidth(int width);
    void refreshPackUi();
    void applyPackToEditors(bool overwriteUser = false);
    void refreshModelCatalog();
    void pickModel();
    void pickLora();
    void clearLora();
    void generateReference();
    void generateTurnaround();
    void lockReference();
    void openInT2I();
    void sendToCharacter();
    void saveProject();
    void loadProject();
    QJsonObject buildPayload(ConceptViewMode view) const;
    QString projectsDir() const;
    ConceptAssetType currentAssetType() const;
    ConceptContentMode currentContentMode() const;
    ConceptViewMode currentViewMode() const;
    QString selectedModelValue() const;
    QString selectedModelDisplay() const;
    QString selectedLoraValue() const;

    QString projectRoot_;
    QString projectName_ = QStringLiteral("concept_ref_01");
    bool advanced_ = false;
    bool busy_ = false;
    bool catalogLoaded_ = false;
    QString lockedImagePath_;
    QString lastOutputPath_;
    QString selectedModelPath_;
    QString selectedModelDisplay_;
    QString selectedLoraPath_;
    QString selectedLoraDisplay_;

    ConceptAssetType assetType_ = ConceptAssetType::CharacterBody;
    ConceptContentMode contentMode_ = ConceptContentMode::Sfw;
    ConceptViewMode viewMode_ = ConceptViewMode::HeroFront;

    QSplitter *mainSplit_ = nullptr;
    QWidget *leftColumn_ = nullptr;
    QWidget *rightColumn_ = nullptr;

    DashboardGlassPanel *heroPanel_ = nullptr;
    QLabel *heroTitle_ = nullptr;
    QLabel *heroSubtitle_ = nullptr;
    QLabel *statusBanner_ = nullptr;
    QProgressBar *progress_ = nullptr;

    QButtonGroup *assetTypeGroup_ = nullptr;
    QButtonGroup *contentModeGroup_ = nullptr;
    QButtonGroup *viewModeGroup_ = nullptr;

    QLineEdit *projectNameEdit_ = nullptr;
    QLabel *modelValueLabel_ = nullptr;
    QPushButton *pickModelBtn_ = nullptr;
    QPushButton *refreshModelsBtn_ = nullptr;
    QLabel *loraValueLabel_ = nullptr;
    QPushButton *pickLoraBtn_ = nullptr;
    QPushButton *clearLoraBtn_ = nullptr;
    QTextEdit *subjectEdit_ = nullptr;
    QTextEdit *positiveEdit_ = nullptr;
    QTextEdit *negativeEdit_ = nullptr;
    QLabel *checklistLabel_ = nullptr;
    QLabel *packSummaryLabel_ = nullptr;

    QLabel *previewLabel_ = nullptr;
    QLabel *previewCaption_ = nullptr;

    QPushButton *applyPackBtn_ = nullptr;
    QPushButton *generateBtn_ = nullptr;
    QPushButton *turnaroundBtn_ = nullptr;
    QPushButton *lockBtn_ = nullptr;
    QPushButton *openT2IBtn_ = nullptr;
    QPushButton *toCharacterBtn_ = nullptr;
    QPushButton *saveBtn_ = nullptr;
    QLabel *actionHint_ = nullptr;

    QWidget *advancedBlock_ = nullptr;
    QCheckBox *randomSeedCheck_ = nullptr;
    QLineEdit *seedEdit_ = nullptr;
    QLineEdit *stepsEdit_ = nullptr;
    QLineEdit *cfgEdit_ = nullptr;
};

} // namespace spellvision::studios
