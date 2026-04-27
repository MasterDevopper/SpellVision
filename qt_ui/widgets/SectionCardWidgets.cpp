#include "SectionCardWidgets.h"

#include <QFrame>
#include <QLabel>
#include <QObject>
#include <QStyle>
#include <QToolButton>
#include <QVBoxLayout>
#include <QWidget>

namespace spellvision::widgets
{

QFrame *createCard(const QString &objectName, QWidget *parent)
{
    auto *frame = new QFrame(parent);
    frame->setObjectName(objectName);
    frame->setFrameShape(QFrame::NoFrame);
    return frame;
}

QLabel *createSectionTitle(const QString &text, QWidget *parent)
{
    auto *label = new QLabel(text, parent);
    label->setObjectName(QStringLiteral("SectionTitle"));
    return label;
}

QLabel *createSectionBody(const QString &text, QWidget *parent)
{
    auto *label = new QLabel(text, parent);
    label->setWordWrap(true);
    label->setObjectName(QStringLiteral("SectionBody"));
    return label;
}

void repolishWidget(QWidget *widget)
{
    if (!widget)
        return;

    if (QStyle *style = widget->style())
    {
        style->unpolish(widget);
        style->polish(widget);
    }

    widget->update();
}

QWidget *makeCollapsibleSection(QVBoxLayout *parentLayout,
                                const QString &title,
                                QWidget *body,
                                bool expanded)
{
    auto *container = new QWidget;
    auto *layout = new QVBoxLayout(container);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(8);

    auto *toggle = new QToolButton(container);
    toggle->setText(title);
    toggle->setCheckable(true);
    toggle->setChecked(expanded);
    toggle->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    toggle->setArrowType(expanded ? Qt::DownArrow : Qt::RightArrow);
    toggle->setObjectName(QStringLiteral("SecondaryActionButton"));

    if (body)
        body->setVisible(expanded);

    QObject::connect(toggle, &QToolButton::toggled, body, [body, toggle](bool checked) {
        if (body)
            body->setVisible(checked);
        toggle->setArrowType(checked ? Qt::DownArrow : Qt::RightArrow);
    });

    layout->addWidget(toggle);
    if (body)
        layout->addWidget(body);
    if (parentLayout)
        parentLayout->addWidget(container);
    return container;
}

} // namespace spellvision::widgets
