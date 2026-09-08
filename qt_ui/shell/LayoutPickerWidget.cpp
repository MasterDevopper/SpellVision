#include "shell/LayoutPickerWidget.h"

#include "ThemeManager.h"
#include "style/SvKit.h"
#include "style/SvStyle.h"

#include <QFocusEvent>
#include <QFrame>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QRegularExpression>
#include <QStyle>
#include <QStyleOption>
#include <QVBoxLayout>

namespace spellvision::shell
{

// Visible everywhere in this file, including the anonymous namespace below (a nested namespace
// sees an enclosing one's using-declarations) and LayoutPickerWidget's own methods further down.
using Layout = ShellLayout::Layout;

namespace
{
using Color = ThemeManager::Color;

const ThemeManager &theme() { return ThemeManager::instance(); }

QString cardObjectName(Layout layout)
{
    return QStringLiteral("LayoutCard_%1")
        .arg(ShellLayout::instance().layoutNames().at(static_cast<int>(layout)));
}

// The diagram alone: a rail block (or a top bar), an inspector column or strip, painted from live
// theme tokens so it can never go stale the way a screenshot would (task 8 brief, step 1). The
// three shapes are bound by the shipped spec table (section 2.1, corrected twice during task 7's
// review) and are carried forward here verbatim rather than re-imagined:
//
//   Instrument -- left rail at the FULL width, the widest of the three; inspector a column of
//                 moderate width, WIDER than the rail -- the shipped shell is a 64 px rail against a
//                 280-460 px inspector, and fix round 1 caught this schematic drawing it inverted
//                 (44 px rail against a 37 px inspector at the fixture size).
//   Canvas     -- left rail COLLAPSED AND NARROW, visibly thinner than Instrument's, which is the
//                 whole point of the layout; inspector a THIN STRIP of tab glyphs, never a column.
//                 Only the COLLAPSED state is drawn -- it is what the user arrives to, and it
//                 sidesteps the overlay-versus-push question entirely: Canvas's inspector PUSHES
//                 open beside the canvas, and a card that drew an opened overlay would advertise a
//                 layout that does not exist.
//   Workspaces -- a horizontal bar across the TOP, no left rail at all; inspector a column like
//                 Instrument's, seated below the bar.
//
// A bare QWidget subclass, so it needs its own PE_Widget fill or it paints with no background at
// all -- the same gotcha shell/SideRail.cpp's paintEvent carries a comment for.
class LayoutThumbnail : public QWidget
{
public:
    LayoutThumbnail(Layout layout, LayoutPickerWidget *picker, QWidget *parent = nullptr)
        : QWidget(parent), layout_(layout), picker_(picker)
    {
        setFixedHeight(64);
        setMinimumWidth(120);
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QStyleOption opt;
        opt.initFrom(this);
        QPainter painter(this);
        style()->drawPrimitive(QStyle::PE_Widget, &opt, &painter, this);
        painter.setRenderHint(QPainter::Antialiasing, true);

        const ThemeManager &t = theme();
        // THE PICKER, not the singleton. Task 9 fix round 1: this line read
        // ShellLayout::instance().layout() while LayoutCard::selected() read
        // picker_->selectedLayout(), and in Deferred mode -- the mode the first-run dialog sets --
        // those two cannot agree. Measured in the real dialog before the fix: clicking Canvas moved
        // the Instrument card by 0.9116 and the Canvas card by 0.9145 while all three thumbnails
        // moved 0.0000, so the user saw the Canvas card framed as chosen with the Instrument card's
        // DIAGRAM still carrying the accent tint and border. It survived six plants because every
        // one of them exercised Immediate mode, where the two readings happen to coincide.
        const bool selected = picker_ && picker_->selectedLayout() == layout_;

        // Fix round 1, M2: this backdrop used to be hand-painted as Surface1 at radiusCard() -- the
        // IDENTICAL recipe SvStyle's paintSurface uses for the card (Surface::Panel) it sits inside,
        // so the thumbnail read as the same plate as its own container. Surface::Inset's own recipe
        // (SvStyle.cpp paintSurface, Surface0 / BorderSubtle / radiusControl -- SvStyle.cpp:318,345)
        // is what a RECESSED region inside a panel is supposed to use; drawn by hand here rather than
        // through kit::setSurface because this widget is a bare QWidget, not a QFrame.
        const qreal pad = 6.0;
        const QRectF backdrop = QRectF(rect()).adjusted(pad, pad, -pad, -pad);
        QPainterPath backdropPath;
        backdropPath.addRoundedRect(backdrop, t.radiusControl(), t.radiusControl());

        painter.setPen(Qt::NoPen);
        painter.setBrush(t.color(Color::Surface0));
        painter.drawPath(backdropPath);
        if (selected)
        {
            // The wave-1 chip fix, applied to the diagram too: an accent TINT over the plate, not a
            // white veil -- a veil moves a light Ivory plate by four levels and reads as nothing.
            painter.setBrush(t.color(Color::AccentSubtle));
            painter.drawPath(backdropPath);
        }
        painter.setPen(QPen(t.color(selected ? Color::Accent : Color::BorderSubtle), 1.0));
        painter.setBrush(Qt::NoBrush);
        painter.drawPath(backdropPath);

        const qreal innerPad = 5.0;
        const QRectF inner = backdrop.adjusted(innerPad, innerPad, -innerPad, -innerPad);
        paintChrome(painter, inner, t);
    }

private:
    void paintChrome(QPainter &painter, const QRectF &inner, const ThemeManager &t) const
    {
        auto chip = [&](const QRectF &r) {
            QPainterPath p;
            p.addRoundedRect(r, t.radiusControl(), t.radiusControl());
            painter.setPen(QPen(t.color(Color::BorderStrong), 1.0));
            painter.setBrush(t.color(Color::Surface2));
            painter.drawPath(p);
        };

        switch (layout_)
        {
        case Layout::Instrument:
        {
            // Rail at the FULL width -- the widest of the three -- inspector a column WIDER than
            // the rail (fix round 1, I3): the shipped shell's proportion is a 64 px rail against a
            // 280-460 px inspector, and this schematic has to point the same direction even though
            // it cannot match the ratio exactly.
            const qreal railW = inner.width() * 0.16;
            const qreal inspectorW = inner.width() * 0.32;
            chip(QRectF(inner.left(), inner.top(), railW, inner.height()));
            chip(QRectF(inner.right() - inspectorW, inner.top(), inspectorW, inner.height()));
            break;
        }
        case Layout::Canvas:
        {
            // Collapsed and narrow -- deliberately a smaller fraction than Instrument's rail above,
            // so the two never share a width. The strip on the right is glyphs, not a column: its
            // fraction stays far below Instrument's inspector fraction on purpose.
            const qreal railW = inner.width() * 0.09;
            const qreal stripW = inner.width() * 0.07;
            chip(QRectF(inner.left(), inner.top(), railW, inner.height()));

            const QRectF strip(inner.right() - stripW, inner.top(), stripW, inner.height());
            chip(strip);
            painter.setPen(Qt::NoPen);
            painter.setBrush(t.color(Color::TextLo));
            const qreal glyph = stripW * 0.4;
            const qreal gx = strip.center().x() - glyph / 2.0;
            for (int i = 0; i < 3; ++i)
            {
                const qreal gy = strip.top() + strip.height() * (0.20 + i * 0.28);
                QPainterPath dot;
                const qreal glyphRadius = t.radiusControl() * 0.4;
                dot.addRoundedRect(QRectF(gx, gy, glyph, glyph), glyphRadius, glyphRadius);
                painter.drawPath(dot);
            }
            break;
        }
        case Layout::Workspaces:
        {
            // No left rail at all -- a bar across the top instead -- inspector a column like
            // Instrument's (same fraction, same width-over-rail relationship), seated below the bar
            // rather than beside it.
            const qreal barH = inner.height() * 0.28;
            chip(QRectF(inner.left(), inner.top(), inner.width(), barH));

            const qreal inspectorW = inner.width() * 0.32;
            const qreal gap = 4.0;
            chip(QRectF(inner.right() - inspectorW, inner.top() + barH + gap,
                        inspectorW, inner.height() - barH - gap));
            break;
        }
        }
    }

    Layout layout_;
    LayoutPickerWidget *picker_ = nullptr;
};

// One card: the thumbnail above, a name and a sentence below, the whole thing clickable AND
// keyboard-reachable (fix round 1, I1 -- this was the only control in Settings with focusPolicy 0,
// no accessible name, no tooltip, against 15 such properties on the neighbouring combo). A QFrame
// so its own background comes from the same svSurface -> PE_Frame path every other Settings card
// uses (kit::setSurface, verified by test_sv_style.cpp's field_panel_only_for_text_edits_and_item_views
// comment trail); the selection tint and edge are painted on top in an override that calls
// QFrame::paintEvent first rather than replacing it, so the base fill is never lost.
class LayoutCard : public QFrame
{
public:
    LayoutCard(Layout layout, LayoutPickerWidget *picker, QWidget *parent = nullptr)
        : QFrame(parent), layout_(layout), picker_(picker)
    {
        const QString name = ShellLayout::instance().layoutNames().at(static_cast<int>(layout));
        const QString description = ShellLayout::instance().layoutDescription(layout);

        setObjectName(cardObjectName(layout));
        spellvision::kit::setSurface(this, style::Surface::Panel);
        setCursor(Qt::PointingHandCursor);

        // I1: keyboard reachability. StrongFocus takes both Tab and a click; Left/Right/Up/Down move
        // between the three cards (keyPressEvent, below) the way a toolbar or a radio group does,
        // Space/Return picks the focused card, and the accessible name/description/tooltip give a
        // screen reader and a mouse-hover user the same information the sighted layout carries.
        setFocusPolicy(Qt::StrongFocus);
        setAccessibleName(QStringLiteral("%1 layout").arg(name));
        setAccessibleDescription(description);
        setToolTip(description);

        const ThemeManager &t = theme();
        auto *column = new QVBoxLayout(this);
        column->setContentsMargins(t.spacing(ThemeManager::Spacing::Card), t.spacing(ThemeManager::Spacing::Card),
                                   t.spacing(ThemeManager::Spacing::Card), t.spacing(ThemeManager::Spacing::Card));
        column->setSpacing(t.spacing(ThemeManager::Spacing::Snug));

        auto *thumbnail = new LayoutThumbnail(layout, picker, this);
        // A generic name reused across all three cards, not a per-layout one: each card's own
        // subtree holds exactly one, so a test scoped to a card (findChild from the card, not from
        // the picker) still gets an unambiguous answer.
        thumbnail->setObjectName(QStringLiteral("LayoutCardThumbnail"));
        nameLabel_ = new QLabel(name, this);
        nameLabel_->setObjectName(QStringLiteral("LayoutCardName"));
        descLabel_ = new QLabel(description, this);
        descLabel_->setObjectName(QStringLiteral("LayoutCardDescription"));
        descLabel_->setWordWrap(true);

        column->addWidget(thumbnail);
        column->addWidget(nameLabel_);
        column->addWidget(descLabel_, 1);

        applyTheme();
        // The labels are coloured from tokens directly (not from a host page's stylesheet class,
        // e.g. #SettingsBody) because this widget is shared with task 9's first-run dialog, which
        // carries no guarantee of Settings' stylesheet -- a card that only looked right under
        // SettingsPage would not really be the shared widget the interface promises.
        connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, [this]() { applyTheme(); });
        // Any real change to the SINGLETON repaints this card's selection state in Immediate mode --
        // including a change made through a DIFFERENT card, or from outside this widget entirely. In
        // Deferred mode selected() reads the picker's own localSelection_ instead, so this connection
        // is harmless there (a repaint that finds nothing changed).
        connect(&ShellLayout::instance(), &ShellLayout::layoutChanged, this, [this](Layout) { update(); });
    }

protected:
    void paintEvent(QPaintEvent *event) override
    {
        QFrame::paintEvent(event);

        const ThemeManager &t = theme();
        QRectF r = QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5);

        if (selected())
        {
            // The wave-1 chip fix (SvStyle.cpp's Role::Chip case): selection is an accent tint over
            // the plate plus an accent edge, not a white veil -- AccentSubtle is a hue shift rather
            // than a luminance one, so it survives Ivory Holograph's near-white plate as well as a
            // dark one. Measured under Ivory Holograph / Hybrid (fix round 1 review): mean ΔLum 13.79
            // across the whole card -- 11.87 in the label band, 12.58 in the margins, 13.58 in the
            // thumbnail (which carries its own, independently-derived tint), 36.05 at the edge drawn
            // here. Wave-1's original chip defect measured 4.
            QPainter painter(this);
            painter.setRenderHint(QPainter::Antialiasing, true);
            QPainterPath path;
            path.addRoundedRect(r, t.radiusCard(), t.radiusCard());

            painter.setPen(Qt::NoPen);
            painter.setBrush(t.color(Color::AccentSubtle));
            painter.drawPath(path);
            painter.setPen(QPen(t.color(Color::Accent), 1.5));
            painter.setBrush(Qt::NoBrush);
            painter.drawPath(path);
        }

        if (hasFocus())
        {
            // A ring independent of selection: an unselected card can still be the keyboard's
            // current stop (Tab landed on it, Space/Return has not fired yet), and that state has to
            // be visible on its own.
            QPainter painter(this);
            painter.setRenderHint(QPainter::Antialiasing, true);
            QPainterPath ring;
            ring.addRoundedRect(r.adjusted(2.0, 2.0, -2.0, -2.0), t.radiusCard(), t.radiusCard());
            painter.setPen(QPen(t.color(Color::AccentHover), 2.0));
            painter.setBrush(Qt::NoBrush);
            painter.drawPath(ring);
        }
    }

    void mouseReleaseEvent(QMouseEvent *event) override
    {
        // The card's own click handler and nothing else -- no description-label update, no page
        // signal into MainWindow glue (that road is the theme-preset one this task was told not to
        // copy). What a pick MEANS is the picker's decision (CommitMode), not this card's.
        if (event->button() == Qt::LeftButton)
        {
            pick();
            event->accept();
            return;
        }
        QFrame::mouseReleaseEvent(event);
    }

    void keyPressEvent(QKeyEvent *event) override
    {
        switch (event->key())
        {
        case Qt::Key_Space:
        case Qt::Key_Return:
        case Qt::Key_Enter:
            pick();
            event->accept();
            return;
        case Qt::Key_Right:
        case Qt::Key_Down:
            focusNextChild();
            event->accept();
            return;
        case Qt::Key_Left:
        case Qt::Key_Up:
            focusPreviousChild();
            event->accept();
            return;
        default:
            break;
        }
        QFrame::keyPressEvent(event);
    }

    void focusInEvent(QFocusEvent *event) override
    {
        QFrame::focusInEvent(event);
        update();
    }

    void focusOutEvent(QFocusEvent *event) override
    {
        QFrame::focusOutEvent(event);
        update();
    }

private:
    bool selected() const { return picker_->selectedLayout() == layout_; }
    void pick() { picker_->reportPick(layout_); }

    void applyTheme()
    {
        const ThemeManager &t = theme();

        nameLabel_->setFont(t.font(ThemeManager::Type::Heading));
        QPalette namePal = nameLabel_->palette();
        namePal.setColor(QPalette::WindowText, t.color(Color::TextHi));
        nameLabel_->setPalette(namePal);

        descLabel_->setFont(t.font(ThemeManager::Type::Body));
        QPalette descPal = descLabel_->palette();
        descPal.setColor(QPalette::WindowText, t.color(Color::TextMid));
        descLabel_->setPalette(descPal);

        update();
    }

    Layout layout_;
    LayoutPickerWidget *picker_ = nullptr;
    QLabel *nameLabel_ = nullptr;
    QLabel *descLabel_ = nullptr;
};

} // namespace

LayoutPickerWidget::LayoutPickerWidget(QWidget *parent)
    : QWidget(parent), localSelection_(ShellLayout::instance().layout())
{
    setObjectName(QStringLiteral("LayoutPickerWidget"));

    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(0, 0, 0, 0);
    row->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    for (Layout layout : {Layout::Instrument, Layout::Canvas, Layout::Workspaces})
        row->addWidget(new LayoutCard(layout, this, this), 1);

    // No blanket forward of ShellLayout::layoutChanged here (fix round 1, I4 -- that used to make
    // layoutPicked fire for a change this widget had nothing to do with, and task 9 connects to this
    // signal). reportPick() below is the only place layoutPicked is emitted, and only for a pick that
    // arrived through one of this widget's own cards.
}

void LayoutPickerWidget::setCommitMode(CommitMode mode)
{
    mode_ = mode;
    // Re-seed from the live value whenever the mode is (re)set, so a dialog that resets the mode
    // before each showing does not carry a stale pick from a previous, dismissed run.
    localSelection_ = ShellLayout::instance().layout();
    update();
}

ShellLayout::Layout LayoutPickerWidget::selectedLayout() const
{
    return mode_ == CommitMode::Immediate ? ShellLayout::instance().layout() : localSelection_;
}

void LayoutPickerWidget::commitSelection()
{
    if (mode_ == CommitMode::Deferred)
        ShellLayout::instance().setLayoutByIndex(static_cast<int>(localSelection_));
}

void LayoutPickerWidget::reportPick(Layout layout)
{
    if (mode_ == CommitMode::Immediate)
    {
        const Layout before = ShellLayout::instance().layout();
        ShellLayout::instance().setLayoutByIndex(static_cast<int>(layout));
        // setLayoutByIndex is a no-op (and silent) on a re-pick of the already-active layout; this
        // widget's own notification follows that same only-on-a-real-change contract rather than
        // firing on every click regardless of outcome.
        if (ShellLayout::instance().layout() != before)
            emit layoutPicked(layout);
        return;
    }

    if (localSelection_ == layout)
        return;
    localSelection_ = layout;
    // Nothing reached ShellLayout, so layoutChanged never fires -- the cards would not otherwise
    // know the picker's own selection moved. Reached by object name rather than by the concrete
    // LayoutCard type: that class carries no Q_OBJECT of its own (it adds no signal or slot), and
    // findChildren<T> requires T to have one -- QFrame's, which LayoutCard inherits unchanged, is
    // enough to reach it for a plain update().
    static const QRegularExpression cardNamePattern(QStringLiteral("^LayoutCard_"));
    for (QFrame *card : findChildren<QFrame *>(cardNamePattern, Qt::FindDirectChildrenOnly))
        card->update();
    emit layoutPicked(layout);
}

void LayoutPickerWidget::paintEvent(QPaintEvent *event)
{
    QStyleOption opt;
    opt.initFrom(this);
    QPainter painter(this);
    style()->drawPrimitive(QStyle::PE_Widget, &opt, &painter, this);
    QWidget::paintEvent(event);
}

} // namespace spellvision::shell
