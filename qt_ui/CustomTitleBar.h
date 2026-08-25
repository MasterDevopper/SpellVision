#pragma once

#include <QPoint>
#include <QRect>
#include <QWidget>

class QEvent;
class QFrame;
class QLabel;
class QToolButton;
class QMouseEvent;
class QContextMenuEvent;
class QResizeEvent;

class CustomTitleBar : public QWidget
{
    Q_OBJECT

public:
    explicit CustomTitleBar(QWidget *parent = nullptr);

    void setWindowTitleText(const QString &text);
    void setContextText(const QString &text);
    void setMaximized(bool maximized);
    // Phase 6: reflect the app's global Simple/Advanced disclosure mode on the segmented toggle
    // (programmatic -- updates button checked state without emitting disclosureModeChangeRequested).
    void setDisclosureMode(bool advanced);

    QRect commandPaletteAnchorRect() const;
    bool isDraggableArea(const QPoint &pos) const;

signals:
    void commandPaletteRequested();
    void disclosureModeChangeRequested(bool advanced); // Phase 6: user clicked Simple/Advanced
    void layoutMenuRequested(const QPoint &globalPos);
    void primarySidebarToggleRequested();
    void bottomPanelToggleRequested();
    void secondarySidebarToggleRequested();
    void minimizeRequested();
    void maximizeRestoreRequested();
    void closeRequested();
    void systemMenuRequested(const QPoint &globalPos);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;
    void contextMenuEvent(QContextMenuEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

private:
    // THEME PILOT (Phase 1 foundation). Re-generates every theme-colored visual this
    // widget draws itself -- the painted menu/window icons (paint case) and the search
    // labels' local stylesheets (string case) -- from the canonical ThemeManager color
    // tokens. Subscribed to ThemeManager::themeChanged in the ctor, so a live theme
    // switch re-colors the title bar with no restart. This is the pattern every later
    // phase applies per-widget: a token-reading refresh method + a themeChanged
    // subscription.
    void applyThemeStyling();
    void reflowForWidth(int width);

    QLabel *logoBadge_ = nullptr;
    QLabel *titleLabel_ = nullptr;
    QLabel *contextLabel_ = nullptr;

    QFrame *searchPill_ = nullptr;
    QLabel *searchIconLabel_ = nullptr;
    QLabel *searchTextLabel_ = nullptr;
    QLabel *searchShortcutLabel_ = nullptr;

    QFrame *modeToggle_ = nullptr;          // Phase 6: Simple/Advanced segmented toggle container
    QToolButton *simpleButton_ = nullptr;
    QToolButton *advancedButton_ = nullptr;

    QToolButton *layoutButton_ = nullptr;
    QToolButton *primarySidebarButton_ = nullptr;
    QToolButton *bottomPanelButton_ = nullptr;
    QToolButton *secondarySidebarButton_ = nullptr;
    QToolButton *minButton_ = nullptr;
    QToolButton *maxButton_ = nullptr;
    QToolButton *closeButton_ = nullptr;
};
