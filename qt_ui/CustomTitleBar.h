#pragma once

#include <QPoint>
#include <QRect>
#include <QWidget>

class QEvent;
class QFrame;
class QLabel;
class QPushButton;
class QToolButton;
class QMouseEvent;
class QContextMenuEvent;

class CustomTitleBar : public QWidget
{
    Q_OBJECT

public:
    explicit CustomTitleBar(QWidget *parent = nullptr);

    void setWindowTitleText(const QString &text);
    void setContextText(const QString &text);
    void setMaximized(bool maximized);

    QRect commandPaletteAnchorRect() const;
    bool isDraggableArea(const QPoint &pos) const;

signals:
    void menuRequested(const QString &menuId, const QPoint &globalPos);
    void commandPaletteRequested();
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

private:
    void emitMenuSignal(const QString &menuId, QWidget *anchor);

    QLabel *logoBadge_ = nullptr;
    QLabel *titleLabel_ = nullptr;
    QLabel *contextLabel_ = nullptr;

    QPushButton *fileButton_ = nullptr;
    QPushButton *editButton_ = nullptr;
    QPushButton *viewButton_ = nullptr;
    QPushButton *generationButton_ = nullptr;
    QPushButton *modelsButton_ = nullptr;
    QPushButton *workflowsButton_ = nullptr;
    QPushButton *toolsButton_ = nullptr;
    QPushButton *helpButton_ = nullptr;

    QFrame *searchPill_ = nullptr;
    QLabel *searchIconLabel_ = nullptr;
    QLabel *searchTextLabel_ = nullptr;
    QLabel *searchShortcutLabel_ = nullptr;

    QToolButton *layoutButton_ = nullptr;
    QToolButton *primarySidebarButton_ = nullptr;
    QToolButton *bottomPanelButton_ = nullptr;
    QToolButton *secondarySidebarButton_ = nullptr;
    QToolButton *minButton_ = nullptr;
    QToolButton *maxButton_ = nullptr;
    QToolButton *closeButton_ = nullptr;
};
