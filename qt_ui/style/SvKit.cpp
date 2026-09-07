#include "style/SvKit.h"

#include "ThemeManager.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QStyle>
#include <QToolButton>
#include <QVBoxLayout>

namespace spellvision::kit
{
namespace
{
void repolish(QWidget *widget)
{
    if (!widget)
        return;
    widget->style()->unpolish(widget);
    widget->style()->polish(widget);
    widget->update();
}
} // namespace

QPushButton *button(style::Role role, const QString &text, const QString &objectName, QWidget *parent)
{
    auto *b = new QPushButton(text, parent);
    b->setObjectName(objectName);
    b->setProperty("svRole", style::SvStyle::roleName(role));
    b->setCursor(Qt::PointingHandCursor);
    return b;
}

QToolButton *chip(const QString &text, const QString &objectName, QWidget *parent)
{
    auto *c = new QToolButton(parent);
    c->setText(text);
    c->setObjectName(objectName);
    c->setCheckable(true);
    c->setAutoRaise(false);
    c->setProperty("svRole", style::SvStyle::roleName(style::Role::Chip));
    c->setCursor(Qt::PointingHandCursor);
    return c;
}

QFrame *card(style::Surface surface, const QString &objectName, QWidget *parent)
{
    auto *f = new QFrame(parent);
    f->setObjectName(objectName);
    f->setFrameShape(QFrame::StyledPanel);
    f->setFrameShadow(QFrame::Plain);
    f->setProperty("svSurface", style::SvStyle::surfaceName(surface));
    return f;
}

QWidget *row(const QString &label, QWidget *control, QWidget *parent)
{
    const auto &theme = ThemeManager::instance();
    auto *host = new QWidget(parent);
    auto *column = new QVBoxLayout(host);
    column->setContentsMargins(0, 0, 0, 0);
    column->setSpacing(0);
    auto *line = new QHBoxLayout();
    line->setContentsMargins(0, theme.spacing(ThemeManager::Spacing::Tight), 0, theme.spacing(ThemeManager::Spacing::Tight));
    line->setSpacing(theme.spacing(ThemeManager::Spacing::Snug));
    auto *caption = new QLabel(label, host);
    caption->setObjectName(QStringLiteral("KitRowLabel"));
    line->addWidget(caption, 0);
    line->addStretch(1);
    if (control)
    {
        control->setParent(host);
        line->addWidget(control, 0);
    }
    column->addLayout(line);
    auto *rule = new QFrame(host);
    rule->setObjectName(QStringLiteral("KitRowRule"));
    rule->setFrameShape(QFrame::HLine);
    rule->setFixedHeight(1);
    column->addWidget(rule);
    return host;
}

void setRole(QWidget *widget, style::Role role)
{
    if (!widget)
        return;
    widget->setProperty("svRole", style::SvStyle::roleName(role));
    repolish(widget);
}

void setSurface(QFrame *frame, style::Surface surface)
{
    if (!frame)
        return;
    frame->setFrameShape(QFrame::StyledPanel);
    frame->setFrameShadow(QFrame::Plain);
    frame->setProperty("svSurface", style::SvStyle::surfaceName(surface));
    repolish(frame);
}

} // namespace spellvision::kit
