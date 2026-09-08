#pragma once

#include <QKeySequence>
#include <QMap>
#include <QPoint>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QBoxLayout;
class QPaintEvent;
class QScrollArea;
class QToolButton;

namespace spellvision::shell
{

// The app's activity rail: the strip of mode buttons the whole shell navigates by. Extracted
// verbatim from MainWindow::createSideRail / MainWindow::createRailButton (spec
// docs/superpowers/specs/2026-09-08-shell-layouts-design.md, section 2.4) so that the rail's shape
// is decided in ONE place. Before this it was decided in two MainWindow methods and read back by a
// third that assumed the answer.
//
// It owns its buttons, their glyphs (re-inked from the theme, so a preset switch regenerates them)
// and -- the reason the class exists -- the answer to WHERE PAGE CONTENT BEGINS. The activity
// drawer computes its own X from the rail's width today, which is correct exactly as long as the
// rail never moves.
//
// setOrientation() is declared here and implemented in task 3 of the wave; this build accepts
// Qt::Vertical only, and everything below is the vertical rail as it has always looked.
class SideRail : public QWidget
{
    Q_OBJECT

public:
    explicit SideRail(QWidget *parent = nullptr);

    // Appends a mode button. `iconName` is the SVG/PNG basename under qt_ui/icons (the mode id, for
    // every mode the shell ships). `toolTip` and `shortcut` are optional so the three-argument form
    // in the spec compiles: with a shortcut the button navigates window-wide and the tooltip carries
    // the key, which is what the rail has always done.
    void addMode(const QString &id,
                 const QString &label,
                 const QString &iconName,
                 const QString &toolTip = QString(),
                 const QKeySequence &shortcut = QKeySequence());

    // A Create / Manage / System boundary. The rail ships FLAT today -- MainWindow does not call
    // this -- so it renders as the hairline the vertical rail would use; task 3 gives the
    // horizontal rail its labelled form from the text kept here.
    void addGroupHeader(const QString &text);

    // Checks the button for `id` and unchecks the rest, through the one rule that has always
    // decided it (ShellNavigationController::updateModeButtonState).
    void setCurrentMode(const QString &id);
    QString currentMode() const { return currentMode_; }

    void setOrientation(Qt::Orientation orientation);
    Qt::Orientation orientation() const { return orientation_; }

    // Where page content begins, in the parent's coordinates: the rail's inner edge. PURELY
    // GEOMETRIC -- a caller that hides the rail (togglePrimarySidebar) still gets the rail's own
    // width back and must decide for itself what a hidden rail means, because a widget that has
    // never been shown is also "not visible" and would otherwise report an origin of zero.
    QPoint contentOrigin() const;

    // The one sanctioned way to reach a rail button from outside. Null for an unknown id.
    QToolButton *buttonFor(const QString &id) const;
    QStringList modeIds() const;

    // The rail's glyphs are re-inked from the active theme, so a preset switch has to regenerate
    // every QIcon -- reloading a stylesheet does not touch one.
    void refreshIcons();

signals:
    void modeActivated(const QString &modeId);

protected:
    // Required, not decorative. A QWidget SUBCLASS does not get its stylesheet background painted
    // for free the way a plain QWidget instance does, so #SideRail's gradient and its right-hand
    // hairline stop being drawn the moment the rail becomes a class. Measured when this was
    // missing: 1.19 % of a 1600x1000 frame, the whole 64 px column, on every page.
    void paintEvent(QPaintEvent *event) override;

private:
    struct ModeEntry
    {
        QString id;
        QString iconName;
        QToolButton *button = nullptr;
    };

    QToolButton *makeButton(const QString &id, const QString &label, const QString &iconName);
    void applyButtonMetrics(QToolButton *button, bool hasIcon) const;

    Qt::Orientation orientation_ = Qt::Vertical;
    QString currentMode_;
    QVector<ModeEntry> modes_;
    QMap<QString, QToolButton *> buttonsById_;
    QStringList groupHeaders_;

    QScrollArea *scroll_ = nullptr;
    QWidget *column_ = nullptr;
    QBoxLayout *columnLayout_ = nullptr;
};

} // namespace spellvision::shell
