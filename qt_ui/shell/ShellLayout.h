#pragma once

#include <QObject>
#include <QString>
#include <QStringList>

namespace spellvision::shell
{

// The whole-app shell arrangement the user is in -- Instrument / Canvas / Workspaces (spec
// docs/superpowers/specs/2026-09-08-shell-layouts-design.md, section 2.2). Mirrors ThemeManager's
// shape (private ctor, instance(), a mutator that saves then emits) so the Settings page has one
// pattern to follow rather than two.
//
// Deliberately NOT part of ThemeManager: a theme decides colour and material, a layout decides
// structure. Merging them would mean a preset could not be worn in every layout, and
// themeChanged() already fans out to every widget that repaints -- a layout change needs a rarer,
// heavier signal that only the shell listens to.
//
// Nothing reads this yet (task 1 of the wave 2 build order). Tasks 5, 8 and 9 wire the rail, the
// shell and Settings/first-run to it.
class ShellLayout : public QObject
{
    Q_OBJECT

public:
    enum class Layout
    {
        Instrument = 0,
        Canvas,
        Workspaces
    };
    Q_ENUM(Layout)

    static ShellLayout &instance();

    Layout layout() const;

    // User-facing copy, fixed by the spec. layoutNames() order matches the Layout enum, so
    // layoutNames()[int(layout())] is always the current layout's name.
    QStringList layoutNames() const;
    QString layoutDescription(Layout layout) const;

    // Reads ui/shellLayout under org DarkDuck / app SpellVision, clamping an absent or
    // out-of-range value to Instrument. Public (unlike ThemeManager::load(), which is private)
    // because tests need to force a reload after writing the setting directly.
    void load();

signals:
    void layoutChanged(Layout layout);

public slots:
    // Writes, saves and emits ONLY on a real change; a no-op set is silent.
    void setLayout(Layout layout);
    // Out-of-range indices (including negative) are ignored rather than crashing.
    void setLayoutByIndex(int index);

private:
    explicit ShellLayout(QObject *parent = nullptr);

    void save() const;

    Layout layout_ = Layout::Instrument;
};

} // namespace spellvision::shell
