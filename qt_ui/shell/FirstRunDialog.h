#pragma once

#include "RuntimeProfile.h"

#include <QDialog>
#include <QString>

class QCheckBox;
class QLabel;
class QPushButton;

namespace spellvision::shell
{

class FirstRunDialog final : public QDialog
{
public:
    enum class Action
    {
        Continue,
        OpenRuntime,
    };

    explicit FirstRunDialog(const QString &projectRoot,
                            bool workerStarting = false,
                            bool comfyStarting = false,
                            QWidget *parent = nullptr);

    Action action() const;
    bool suppressFuturePrompts() const;

private:
    void browseModelsRoot();
    void browseOutputFolder();
    void refreshFolderLabels();
    void refreshChecks();
    void persistFolders();

    Action action_ = Action::Continue;
    RuntimeProfile profile_;
    QString outputFolder_;
    bool otherRequiredReady_ = false;
    bool workerStarting_ = false;
    bool comfyStarting_ = false;
    QCheckBox *suppressCheck_ = nullptr;
    QPushButton *continueButton_ = nullptr;
    QLabel *modelsPathLabel_ = nullptr;
    QLabel *outputPathLabel_ = nullptr;
    QLabel *modelsCheckDetail_ = nullptr;
    QLabel *modelsCheckStatus_ = nullptr;
    QLabel *outputCheckDetail_ = nullptr;
    QLabel *outputCheckStatus_ = nullptr;
    QLabel *workerCheckDetail_ = nullptr;
    QLabel *workerCheckStatus_ = nullptr;
    QLabel *comfyCheckDetail_ = nullptr;
    QLabel *comfyCheckStatus_ = nullptr;
};

} // namespace spellvision::shell
