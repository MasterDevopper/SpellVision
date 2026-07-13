#pragma once

#include <QDialog>
#include <QVector>

#include <functional>

class QListWidget;
class QListWidgetItem;
class QLineEdit;

// VSCode-style command palette. Holds a structured command set (id / title / category / optional
// shortcut / self-contained action) and fuzzy-matches the query as a subsequence so "t2v" hits
// "Text to Video" and "juggXL" hits "Juggernaut-XL_v9". The owner (MainWindow) builds the command
// list and drives the second-level model/LoRA picker by calling setCommands() again from a command's
// action (see keepOpen + setBackHandler).
class CommandPaletteDialog : public QDialog
{
    Q_OBJECT

public:
    struct Command
    {
        QString id;                    // stable id (telemetry / tests); not shown
        QString title;                 // primary display text
        QString subtitle;              // dim right-side detail, e.g. "LoRA · sdxl" for model rows
        QString category;              // group header text (empty groups skip the header)
        QString keywords;              // extra fuzzy-match aliases (not shown), e.g. "t2v" for "Text to Video"
        QString shortcut;              // optional keycap hint, e.g. "Ctrl+Shift+P"
        std::function<void()> action;  // invoked on activate
        bool keepOpen = false;         // true: don't close after action (it repopulates for a submode)
    };

    explicit CommandPaletteDialog(QWidget *parent = nullptr);

    // Swap the active command set and reset the query/selection. `placeholder` sets the search hint.
    void setCommands(const QVector<Command> &commands, const QString &placeholder = QString());

    // When set, Escape returns here (submode -> top level) instead of closing the dialog. Cleared on
    // each setCommands() unless re-set by the caller.
    void setBackHandler(std::function<void()> onBack);

protected:
    void keyPressEvent(QKeyEvent *event) override;
    void showEvent(QShowEvent *event) override;

private slots:
    void filterCommands(const QString &text);
    void activateCurrent();
    void activateItem(QListWidgetItem *item);

private:
    void updateResults(const QString &query);
    void applyThemeStyling(); // token-based stylesheet, re-applied on themeChanged

    // Subsequence fuzzy score: -1 when `query` is not an (in-order, case-insensitive) subsequence of
    // `text`; otherwise a positive score that rewards consecutive runs and word-boundary starts.
    static int fuzzyScore(const QString &query, const QString &text);

    QLineEdit *searchBox_ = nullptr;
    QListWidget *resultsList_ = nullptr;
    QVector<Command> commands_;
    std::function<void()> backHandler_;
};
