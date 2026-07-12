#include "CommandPaletteDialog.h"
#include "ThemeManager.h"

#include <QApplication>
#include <QKeyEvent>
#include <QLineEdit>
#include <QListWidget>
#include <QListWidgetItem>
#include <QVBoxLayout>

CommandPaletteDialog::CommandPaletteDialog(QWidget *parent)
    : QDialog(parent)
{
    setWindowFlags(Qt::FramelessWindowHint | Qt::Dialog);
    setModal(true);

    setMinimumWidth(820);
    setMaximumWidth(1180);
    resize(940, 460);

    setObjectName(QStringLiteral("CommandPaletteDialog"));
    applyThemeStyling();
    connect(&ThemeManager::instance(), &ThemeManager::themeChanged, this, &CommandPaletteDialog::applyThemeStyling);

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card), ThemeManager::instance().spacing(ThemeManager::Spacing::Card));
    layout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));

    searchBox_ = new QLineEdit(this);
    searchBox_->setPlaceholderText(QStringLiteral("Type a command..."));

    resultsList_ = new QListWidget(this);
    resultsList_->setMinimumHeight(320);
    resultsList_->setUniformItemSizes(false);

    layout->addWidget(searchBox_);
    layout->addWidget(resultsList_, 1);

    connect(searchBox_, &QLineEdit::textChanged,
            this, &CommandPaletteDialog::filterCommands);
    connect(searchBox_, &QLineEdit::returnPressed,
            this, &CommandPaletteDialog::activateCurrent);
    connect(resultsList_, &QListWidget::itemActivated,
            this, &CommandPaletteDialog::activateItem);
    connect(resultsList_, &QListWidget::itemDoubleClicked,
            this, &CommandPaletteDialog::activateItem);

    searchBox_->setFocus();
}

void CommandPaletteDialog::applyThemeStyling()
{
    // Phase 5 correction batch: this dialog used a stale hardcoded GREY ramp (#202531 /
    // #111622 / #161c28 surfaces, #e7eaf0/#dfe6ef text) with no theme wiring at all.
    // Migrated to canonical Doc 16 tokens + subscribed to themeChanged, so the palette is
    // on-palette and theme-switches. (The selected-item violet was already ~on-brand.)
    const auto &theme = ThemeManager::instance();
    using C = ThemeManager::Color;
    setStyleSheet(QStringLiteral(
        "#CommandPaletteDialog { background: %1; border: 1px solid %2; border-radius: 10px; }"
        "QLineEdit { font-size: 14px; min-height: 42px; background: %3; color: %4;"
        " border: 1px solid %2; border-radius: 8px; padding: 8px 10px; }"
        "QListWidget { font-size: 12px; background: %5; color: %4; border: 1px solid %6;"
        " border-radius: 8px; outline: none; }"
        "QListWidget::item { padding: 12px 12px; border-bottom: 1px solid %7; }"
        "QListWidget::item:selected { background: %8; }")
        .arg(theme.css(C::Surface3))      // %1 dialog bg (overlay)
        .arg(theme.css(C::BorderStrong))  // %2 dialog + input border
        .arg(theme.css(C::Surface0))      // %3 input bg (recessed)
        .arg(theme.css(C::TextHi))        // %4 input + list text
        .arg(theme.css(C::Surface1))      // %5 list bg
        .arg(theme.css(C::Border))        // %6 list border
        .arg(theme.css(C::BorderSubtle))  // %7 item divider
        .arg(theme.css(C::AccentGlow)));  // %8 selected item (was ~violet already)
}

void CommandPaletteDialog::setCommands(const QStringList &commands)
{
    allCommands_ = commands;
    updateResults(QString());
}

void CommandPaletteDialog::filterCommands(const QString &text)
{
    updateResults(text);
}

void CommandPaletteDialog::updateResults(const QString &query)
{
    resultsList_->clear();

    for (const QString &cmd : allCommands_)
    {
        if (query.isEmpty() || cmd.contains(query, Qt::CaseInsensitive))
            resultsList_->addItem(cmd);
    }

    if (resultsList_->count() > 0)
        resultsList_->setCurrentRow(0);
}

void CommandPaletteDialog::activateCurrent()
{
    activateItem(resultsList_ ? resultsList_->currentItem() : nullptr);
}

void CommandPaletteDialog::activateItem(QListWidgetItem *item)
{
    if (!item)
        return;

    emit commandTriggered(item->text());
    accept();
}