#include "shell/LayoutPickerWidget.h"

#include "ThemeManager.h"
#include "style/SvKit.h"
#include "style/SvStyle.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
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
//                 moderate width.
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
    explicit LayoutThumbnail(Layout layout, QWidget *parent = nullptr)
        : QWidget(parent), layout_(layout)
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
        const bool selected = ShellLayout::instance().layout() == layout_;

        const qreal pad = 6.0;
        const QRectF backdrop = QRectF(rect()).adjusted(pad, pad, -pad, -pad);
        QPainterPath backdropPath;
        backdropPath.addRoundedRect(backdrop, t.radiusCard(), t.radiusCard());

        painter.setPen(Qt::NoPen);
        painter.setBrush(t.color(Color::Surface1));
        painter.drawPath(backdropPath);
        if (selected)
        {
            // The wave-1 chip fix, applied to the diagram too: an accent TINT over the plate, not a
            // white veil -- a veil moves a light Ivory plate by four levels and reads as nothing.
            painter.setBrush(t.color(Color::AccentSubtle));
            painter.drawPath(backdropPath);
        }
        painter.setPen(QPen(t.color(selected ? Color::Accent : Color::Border), 1.0));
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
            // Rail at the FULL width -- the widest of the three -- inspector a column of moderate
            // width. Fractions rather than the real shell's 64 px: this is a schematic, not a ruler.
            const qreal railW = inner.width() * 0.24;
            const qreal inspectorW = inner.width() * 0.20;
            chip(QRectF(inner.left(), inner.top(), railW, inner.height()));
            chip(QRectF(inner.right() - inspectorW, inner.top(), inspectorW, inner.height()));
            break;
        }
        case Layout::Canvas:
        {
            // Collapsed and narrow -- deliberately a smaller fraction than Instrument's rail above,
            // so the two never share a width. The strip on the right is glyphs, not a column.
            const qreal railW = inner.width() * 0.11;
            const qreal stripW = inner.width() * 0.09;
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
            // Instrument's, seated below the bar rather than beside it.
            const qreal barH = inner.height() * 0.28;
            chip(QRectF(inner.left(), inner.top(), inner.width(), barH));

            const qreal inspectorW = inner.width() * 0.20;
            const qreal gap = 4.0;
            chip(QRectF(inner.right() - inspectorW, inner.top() + barH + gap,
                        inspectorW, inner.height() - barH - gap));
            break;
        }
        }
    }

    Layout layout_;
};

// One card: the thumbnail above, a name and a sentence below, the whole thing clickable. A QFrame
// so its own background comes from the same svSurface -> PE_Frame path every other Settings card
// uses (kit::setSurface, verified by test_sv_style.cpp's field_panel_only_for_text_edits_and_item_views
// comment trail); the selection tint and edge are painted on top in an override that calls
// QFrame::paintEvent first rather than replacing it, so the base fill is never lost.
class LayoutCard : public QFrame
{
public:
    LayoutCard(Layout layout, QWidget *parent = nullptr)
        : QFrame(parent), layout_(layout)
    {
        setObjectName(cardObjectName(layout));
        spellvision::kit::setSurface(this, style::Surface::Panel);
        setCursor(Qt::PointingHandCursor);

        const ThemeManager &t = theme();
        auto *column = new QVBoxLayout(this);
        column->setContentsMargins(t.spacing(ThemeManager::Spacing::Card), t.spacing(ThemeManager::Spacing::Card),
                                   t.spacing(ThemeManager::Spacing::Card), t.spacing(ThemeManager::Spacing::Card));
        column->setSpacing(t.spacing(ThemeManager::Spacing::Snug));

        auto *thumbnail = new LayoutThumbnail(layout, this);
        // A generic name reused across all three cards, not a per-layout one: each card's own
        // subtree holds exactly one, so a test scoped to a card (findChild from the card, not from
        // the picker) still gets an unambiguous answer.
        thumbnail->setObjectName(QStringLiteral("LayoutCardThumbnail"));
        nameLabel_ = new QLabel(ShellLayout::instance().layoutNames().at(static_cast<int>(layout)), this);
        nameLabel_->setObjectName(QStringLiteral("LayoutCardName"));
        descLabel_ = new QLabel(ShellLayout::instance().layoutDescription(layout), this);
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
        // Any real change repaints this card's selection state -- including a change made through a
        // DIFFERENT card, or from outside this widget entirely.
        connect(&ShellLayout::instance(), &ShellLayout::layoutChanged, this, [this](Layout) { update(); });
    }

protected:
    void paintEvent(QPaintEvent *event) override
    {
        QFrame::paintEvent(event);

        if (ShellLayout::instance().layout() != layout_)
            return;

        // The wave-1 chip fix (SvStyle.cpp's Role::Chip case): selection is an accent tint over the
        // plate plus an accent edge, not a white veil -- AccentSubtle is a hue shift rather than a
        // luminance one, so it survives Ivory Holograph's near-white plate as well as a dark one.
        // The tint only reaches the margins and the label area here -- the thumbnail above paints
        // itself opaquely over its own region and carries the identical tint independently -- but
        // the edge, drawn at the card's own outer boundary where nothing else paints, carries the
        // signal uniformly across the whole card regardless of what is laid out inside it.
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);
        const ThemeManager &t = theme();
        QRectF r = QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5);
        QPainterPath path;
        path.addRoundedRect(r, t.radiusCard(), t.radiusCard());

        painter.setPen(Qt::NoPen);
        painter.setBrush(t.color(Color::AccentSubtle));
        painter.drawPath(path);
        painter.setPen(QPen(t.color(Color::Accent), 1.5));
        painter.setBrush(Qt::NoBrush);
        painter.drawPath(path);
    }

    void mouseReleaseEvent(QMouseEvent *event) override
    {
        // The card's own click handler and nothing else -- no description-label update, no page
        // signal into MainWindow glue (that road is the theme-preset one this task was told not to
        // copy). Every subscriber, including this card's own selection paint, follows off
        // layoutChanged the way every Surface Style subscriber already follows setStyleByIndex.
        if (event->button() == Qt::LeftButton)
        {
            ShellLayout::instance().setLayoutByIndex(static_cast<int>(layout_));
            event->accept();
            return;
        }
        QFrame::mouseReleaseEvent(event);
    }

private:
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
    QLabel *nameLabel_ = nullptr;
    QLabel *descLabel_ = nullptr;
};

} // namespace

LayoutPickerWidget::LayoutPickerWidget(QWidget *parent)
    : QWidget(parent)
{
    setObjectName(QStringLiteral("LayoutPickerWidget"));

    auto *row = new QHBoxLayout(this);
    row->setContentsMargins(0, 0, 0, 0);
    row->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    for (Layout layout : {Layout::Instrument, Layout::Canvas, Layout::Workspaces})
        row->addWidget(new LayoutCard(layout, this), 1);

    // Signal-to-signal forwarding: layoutChanged and layoutPicked share a signature, and every real
    // change to the singleton -- through a card in THIS widget, through another instance, through
    // anything else -- is a pick a consumer of this widget needs to hear about.
    connect(&ShellLayout::instance(), &ShellLayout::layoutChanged, this, &LayoutPickerWidget::layoutPicked);
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
