#pragma once

// Inspiration — moodboard of recent outputs with KEEP/NO owner-eye marks.
#include "EyePickStore.h"

#include <QJsonObject>
#include <QString>
#include <QWidget>

class QComboBox;
class QDialog;
class QKeyEvent;
class QLabel;
class QLineEdit;
class QPushButton;
class QTextEdit;
class OutputCardModel;

namespace spellvision::assets
{
class ModelCardView;
class ModelThumbnailCache;
class ModelCardDelegate;
}

class InspirationPage : public QWidget
{
    Q_OBJECT

public:
    explicit InspirationPage(QWidget *parent = nullptr);

    void setProjectRoot(const QString &root);
    void refreshGallery();
    void keyPressEvent(QKeyEvent *event) override;

signals:
    void navigateRequested(const QString &modeId);
    void sendToGenerationRequested(const QString &modeId, const QJsonObject &draft);
    void openHistoryRequested();

private:
    void buildUi();
    void applyTheme();
    void onSelectionChanged();
    void sendToT2I();
    void sendToI2I();
    void useAsHomeStarter();
    void applyPick(const QString &mark);
    void advanceSelection();
    void exportPicks();
    void addHuntFolder();
    void clearHuntFolders();
    void persistHuntFolders();
    void restoreHuntFolders();
    void pinTeacherStill();
    void refreshTeacherStill();
    void refreshSelectedStill();
    void openSelectedLightbox();
    bool eventFilter(QObject *watched, QEvent *event) override;
    QJsonObject loadSidecarForPath(const QString &mediaPath) const;

    EyePickStore pickStore_;
    QString projectRoot_;
    QString selectedPath_;
    QString selectedModeId_;
    QString teacherStillPath_;

    OutputCardModel *galleryModel_ = nullptr;
    spellvision::assets::ModelThumbnailCache *thumbCache_ = nullptr;
    spellvision::assets::ModelCardDelegate *cardDelegate_ = nullptr;
    spellvision::assets::ModelCardView *galleryView_ = nullptr;

    QLabel *heroTitle_ = nullptr;
    QLabel *teacherStillLabel_ = nullptr;
    QLabel *teacherPathLabel_ = nullptr;
    QPushButton *pinTeacherButton_ = nullptr;
    QLabel *metaLabel_ = nullptr;
    QLabel *selectedStillLabel_ = nullptr;
    QDialog *lightbox_ = nullptr;
    QLabel *lightboxImage_ = nullptr;
    QTextEdit *promptEdit_ = nullptr;
    QTextEdit *negativeEdit_ = nullptr;
    QLineEdit *filterEdit_ = nullptr;
    QComboBox *pickFilterCombo_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
    QPushButton *sendT2IButton_ = nullptr;
    QPushButton *sendI2IButton_ = nullptr;
    QPushButton *keepButton_ = nullptr;
    QPushButton *noButton_ = nullptr;
    QPushButton *exportPicksButton_ = nullptr;
    QPushButton *addHuntFolderButton_ = nullptr;
    QPushButton *clearHuntFoldersButton_ = nullptr;
    QPushButton *openHistoryButton_ = nullptr;
    QLabel *emptyHint_ = nullptr;
};
