#pragma once

// Model Library Arc — S1 (design doc 22, Amendment A). The card grid view: a virtualized QListView
// in IconMode that reflows on resize. Hover reveals two real buttons (Load Model / Add LoRA + Inspect)
// via a floating overlay positioned over the hovered card's preview — kept off the delegate so paint
// stays fast. A short hide-debounce bridges the gap between the viewport and the overlay so the
// buttons don't vanish as the cursor moves onto them.

#include <QListView>
#include <QPersistentModelIndex>

class QFrame;
class QPushButton;
class QTimer;

namespace spellvision::assets
{

class ModelCardView : public QListView
{
    Q_OBJECT
public:
    // Optional roles a model may expose to relabel the hover overlay (models don't, so they fall back
    // to the type-based labels). Lets an outputs model reuse this view with "Open" / "Send to I2I"
    // buttons instead of "Load Model" / "Inspect", without touching the delegate. High UserRole offsets
    // so they never collide with ModelCardModel's roles.
    enum OverlayRole
    {
        PrimaryActionLabelRole = Qt::UserRole + 40,
        PrimaryActionEnabledRole,
        SecondaryActionLabelRole,
        SecondaryActionEnabledRole
    };

    explicit ModelCardView(QWidget *parent = nullptr);

signals:
    void loadRequested(const QModelIndex &index);    // primary action (Load Model / Add LoRA)
    void inspectRequested(const QModelIndex &index);
    void favoriteToggleRequested(const QModelIndex &index);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseDoubleClickEvent(QMouseEvent *event) override;

private:
    void buildOverlay();
    void applyOverlayStyle();
    void showOverlayFor(const QModelIndex &index);
    void configureOverlayFor(const QModelIndex &index);
    void positionOverlay(const QModelIndex &index);
    void hideOverlay();

    QFrame *overlay_ = nullptr;
    QPushButton *primaryButton_ = nullptr;
    QPushButton *inspectButton_ = nullptr;
    QTimer *hideTimer_ = nullptr;
    QPersistentModelIndex hoverIndex_;
};

} // namespace spellvision::assets
