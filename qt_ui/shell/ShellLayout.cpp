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
    // Anything unreadable falls back to Instrument rather than being clamped INTO range. Clamping
    // was the first spelling and it sent a stored 99 to Workspaces -- the last layout, chosen by
    // nothing but its position in the enum. A value this function does not recognise is a value
    // whose meaning is gone, and the honest reading of it is the default, which is also the layout
    // the app is designed in. This matters on a downgrade: a build that knows fewer layouts than
    // the one that wrote the key would otherwise silently promote the user to the highest it has.
    const bool known = value >= 0 && value < layoutNames().size();
    layout_ = known ? static_cast<Layout>(value) : Layout::Instrument;
}

void ShellLayout::save() const
{
    QSettings settings(QStringLiteral("DarkDuck"), QStringLiteral("SpellVision"));
    settings.setValue(QStringLiteral("ui/shellLayout"), static_cast<int>(layout_));
}

} // namespace spellvision::shell
