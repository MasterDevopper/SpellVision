#pragma once

#include "RuntimeProfile.h"

#include <QDialog>
#include <QString>

class QCheckBox;
class QLabel;
class QPushButton;
class QStackedWidget;

namespace spellvision::shell
{

class LayoutPickerWidget;

// Two pages, in this order: the shell-layout picker, then the environment checklist (spec
// docs/superpowers/specs/2026-09-08-shell-layouts-design.md, section 2.7). The layout comes first
// because it is the only question here the user answers about the app itself rather than about
// their machine, and because a checklist is a poor first impression of a creative tool.
//
// The picker is the SAME widget Settings hosts, in CommitMode::Deferred: a pick moves the widget's
// own selection and nothing else until one of the two exit actions calls commitSelection(). That is
// what makes section 2.7's promise -- "a user who dismisses it keeps Instrument, which is the
// default anyway, so dismissal is never a trap" -- a property of the code rather than a sentence in
// a document. An Immediate picker would write ui/shellLayout the moment a card was clicked, and a
// user who then closed the dialog would be left in a layout they never confirmed.
class FirstRunDialog final : public QDialog
{
public:
    enum class Action
    {
        Continue,
        OpenRuntime,
    };

    // Page order is a contract, not an implementation detail -- the spec fixes it and a test asserts
    // it, so the indices are named rather than spelled 0 and 1 at four call sites.
    enum class Page
    {
        Layout = 0,
        Checklist = 1,
    };

    explicit FirstRunDialog(const QString &projectRoot,
                            bool workerStarting = false,
                            bool comfyStarting = false,
                            QWidget *parent = nullptr);

    Action action() const;
    bool suppressFuturePrompts() const;

    // What the picker is showing. Not a QSettings read: in Deferred mode the setting has not been
    // written yet, which is the whole point.
    int currentPageIndex() const;

private:
    void showPage(Page page);
    void commitLayoutChoice();
    void browseModelsRoot();
    void browseOutputFolder();
    void refreshFolderLabels();
    void refreshChecks();
    void persistFolders();
    void startReachabilityProbes();
    void applyProbeResults(bool workerReady, bool comfyListening);

    Action action_ = Action::Continue;
    RuntimeProfile profile_;
    QString outputFolder_;
    bool otherRequiredReady_ = false;
    bool workerStarting_ = false;
    bool comfyStarting_ = false;
    bool probeInFlight_ = false;
    bool lastWorkerReady_ = false;
    bool lastComfyListening_ = false;
    QCheckBox *suppressCheck_ = nullptr;
    QStackedWidget *pages_ = nullptr;
    LayoutPickerWidget *layoutPicker_ = nullptr;
    QPushButton *backButton_ = nullptr;
    QPushButton *nextButton_ = nullptr;
    QPushButton *runtimeButton_ = nullptr;
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
