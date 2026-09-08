#pragma once

#include "shell/ShellLayout.h"

#include <QObject>
#include <QVector>

class QTextEdit;
class QFrame;
class CockpitInspector;

namespace spellvision::generation
{

// How the cockpit arranges ITSELF for a shell layout (spec
// docs/superpowers/specs/2026-09-08-shell-layouts-design.md, section 2.6). Instrument and
// Workspaces are the shape the page was built in; Canvas gives the room to the image -- the prompt
// folds to a single line that grows back the moment it is focused, and the inspector collapses to a
// strip of tab glyphs.
//
// It is a separate object for two reasons, and the second is the load-bearing one.
//
// ImageGenerationPage.cpp sits against a 3000-line ceiling that a sweep enforces, so the arranging
// had to live somewhere; that is the boring reason. The real one is that a fold is only worth
// anything if it UNFOLDS to exactly what it left, and the surest way to guarantee that is for the
// height the cockpit is BUILT with and the height a fold RESTORES to come out of one function.
// applyPromptEnvelope() is that function: the page calls it at construction for three lines, and
// this class calls it for one and back to three. Nothing remembers a number, so nothing can
// remember a stale one.
//
// NOTHING HERE IS REBUILT. The fold is a min/max height on a QTextEdit that already exists, the
// card's padding is a margin on the layout it already has, and the inspector hides its content
// rather than dropping it. A layout switch may not cost the user a half-typed prompt or a control
// they set (`layout-switch-is-not-a-rebuild`), so the method below is named applyShellLayout on
// purpose: that ratchet reads the body of every function with that name, and a helper called from
// MainWindow's would otherwise be a hole in it.
class CockpitLayout : public QObject
{
    Q_OBJECT

public:
    // The prompt's built height, in lines of its own type. Public because the page builds the
    // prompt with it and this class folds against it -- one number, one owner.
    static constexpr int kPromptLines = 3;
    // What "folded to a single line" means. One line of the same type, through the same formula.
    static constexpr int kFoldedLines = 1;

    CockpitLayout(QFrame *promptCard,
                  QTextEdit *promptEdit,
                  QTextEdit *negativeEdit,
                  CockpitInspector *inspector,
                  QObject *parent = nullptr);

    // Instrument / Workspaces restore the built arrangement; Canvas folds and collapses. Idempotent
    // and reversible: calling it twice with the same layout costs nothing, and calling it with the
    // previous one puts the cockpit back exactly as it was.
    void applyShellLayout(spellvision::shell::ShellLayout::Layout layout);

    // For the test, and for anything that needs to know the prompt is currently a line rather than
    // a paragraph. A state a test cannot read is a state a test cannot check.
    bool isFolded() const { return folded_; }

    // A prompt field's height envelope, measured from ITS OWN polished type rather than assumed.
    // min == max on purpose: the prompt is a fixed window onto a document that scrolls, not a field
    // that grows with what is typed into it.
    static void applyPromptEnvelope(QTextEdit *edit, int lines = kPromptLines);

protected:
    // FocusIn grows the prompt back; FocusOut folds it again -- but only after the event loop has
    // turned, because at FocusOut time the widget that is about to HAVE the focus does not have it
    // yet, and a prompt that folded while the user tabbed from it into the negative field would
    // fold under the cursor.
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void setFolded(bool folded);
    bool aPromptHasFocus() const;

    QFrame *promptCard_ = nullptr;
    QVector<QTextEdit *> edits_;
    CockpitInspector *inspector_ = nullptr;
    bool canvas_ = false;
    bool folded_ = false;
};

} // namespace spellvision::generation
