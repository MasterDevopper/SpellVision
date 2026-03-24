#pragma once

#include <QString>
#include <QWidget>

class QBoxLayout;
class QButtonGroup;
class QGridLayout;
class QLabel;
class QPushButton;
class QResizeEvent;
class QScrollArea;
class QWidget;

class HomePage : public QWidget
{
    Q_OBJECT

public:
    explicit HomePage(QWidget *parent = nullptr);

    void setRuntimeSummary(const QString &runtimeName,
                           int runningCount,
                           int pendingCount,
                           int errorCount,
                           const QString &vramText,
                           const QString &modelText,
                           const QString &loraText,
                           const QString &progressText,
                           int progressPercent);

signals:
    void modeRequested(const QString &modeId);
    void managerRequested(const QString &managerId);

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    QWidget *createWorkflowPreviewCard(const QString &title,
                                       const QString &subtitle,
                                       const QString &modeId,
                                       const QString &sourceLabel,
                                       const QString &buttonText);
    QWidget *createQuickModeCard(const QString &title,
                                 const QString &subtitle,
                                 const QString &modeId);
    QWidget *createRecentOutputCard(const QString &title,
                                    const QString &subtitle,
                                    const QString &modeId);
    void selectMode(const QString &modeId);
    void previewStarter(const QString &title,
                        const QString &subtitle,
                        const QString &modeId,
                        const QString &sourceLabel);
    void updateHero();
    void updateResponsiveLayout();
    void applyTheme();

    QString currentMode_ = QStringLiteral("t2i");
    QString starterTitle_;
    QString starterSubtitle_;
    QString starterSource_;

    QScrollArea *scrollArea_ = nullptr;
    QWidget *contentWidget_ = nullptr;

    QBoxLayout *heroSplitLayout_ = nullptr;
    QBoxLayout *heroContentLayout_ = nullptr;
    QBoxLayout *discoveryLayout_ = nullptr;
    QGridLayout *launcherGrid_ = nullptr;
    QGridLayout *quickGenerateGrid_ = nullptr;
    QGridLayout *recentOutputsGrid_ = nullptr;
    QGridLayout *favoritesGrid_ = nullptr;

    QButtonGroup *modeButtonGroup_ = nullptr;

    QLabel *heroEyebrowLabel_ = nullptr;
    QLabel *heroTitleLabel_ = nullptr;
    QLabel *heroSubtitleLabel_ = nullptr;
    QLabel *dependencyBannerLabel_ = nullptr;
    QLabel *heroInputLabel_ = nullptr;
    QLabel *stackSummaryLabel_ = nullptr;
    QLabel *heroHintLabel_ = nullptr;

    QLabel *activeCheckpointValue_ = nullptr;
    QLabel *activeLoraValue_ = nullptr;
    QLabel *activeQueueValue_ = nullptr;
    QLabel *activeRuntimeValue_ = nullptr;

    QPushButton *primaryActionButton_ = nullptr;

    QWidget *workflowLauncherCard_ = nullptr;
    QWidget *quickGenerateCard_ = nullptr;
    QWidget *recentOutputsCard_ = nullptr;
    QWidget *favoritesCard_ = nullptr;
    QWidget *activeModelsCard_ = nullptr;

    QWidget *launcherRecentCard_ = nullptr;
    QWidget *launcherImportedCard_ = nullptr;

    QWidget *quickT2iCard_ = nullptr;
    QWidget *quickI2iCard_ = nullptr;
    QWidget *quickT2vCard_ = nullptr;
    QWidget *quickI2vCard_ = nullptr;

    QWidget *recentOutputPortrait_ = nullptr;
    QWidget *recentOutputLandscape_ = nullptr;
    QWidget *recentOutputVideo_ = nullptr;

    QWidget *favoritePortraitCard_ = nullptr;
    QWidget *favoriteLandscapeCard_ = nullptr;
    QWidget *favoriteCityCard_ = nullptr;
};
