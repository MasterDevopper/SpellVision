#include "shell/ShellLayout.h"

#include <QSettings>

namespace spellvision::shell
{

ShellLayout &ShellLayout::instance()
{
    static ShellLayout manager;
    return manager;
}

ShellLayout::ShellLayout(QObject *parent)
    : QObject(parent)
{
    load();
}

ShellLayout::Layout ShellLayout::layout() const
{
    return layout_;
}

QStringList ShellLayout::layoutNames() const
{
    return {QStringLiteral("Instrument"), QStringLiteral("Canvas"), QStringLiteral("Workspaces")};
}

QString ShellLayout::layoutDescription(Layout layout) const
{
    switch (layout)
    {
    case Layout::Instrument:
        return QStringLiteral("A dense left rail with the inspector beside your work. The default.");
    case Layout::Canvas:
        return QStringLiteral("The image takes the room. Prompt and controls fold away until you need them.");
    case Layout::Workspaces:
        return QStringLiteral("Modes across the top, so wide pages like Models and History get the full width.");
    }
    return {};
}

void ShellLayout::setLayout(Layout layout)
{
    if (layout_ == layout)
        return;

    layout_ = layout;
    save();
    emit layoutChanged(layout_);
}

void ShellLayout::setLayoutByIndex(int index)
{
    if (index < 0 || index >= layoutNames().size())
        return;

    setLayout(static_cast<Layout>(index));
}

void ShellLayout::load()
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    const int value = settings.value(QStringLiteral("ui/shellLayout"), static_cast<int>(Layout::Instrument)).toInt();
    layout_ = static_cast<Layout>(qBound(0, value, layoutNames().size() - 1));
}

void ShellLayout::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("ui/shellLayout"), static_cast<int>(layout_));
}

} // namespace spellvision::shell
