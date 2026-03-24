#include "CommandPaletteDialog.h"

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
    setStyleSheet(
        "#CommandPaletteDialog {"
        "  background: #202531;"
        "  border: 1px solid #3b4356;"
        "  border-radius: 10px;"
        "}"
        "QLineEdit {"
        "  font-size: 14px;"
        "  min-height: 42px;"
        "  background: #111622;"
        "  color: #e7eaf0;"
        "  border: 1px solid #31384a;"
        "  border-radius: 8px;"
        "  padding: 8px 10px;"
        "}"
        "QListWidget {"
        "  font-size: 13px;"
        "  background: #161c28;"
        "  color: #dfe6ef;"
        "  border: 1px solid #2b3446;"
        "  border-radius: 8px;"
        "  outline: none;"
        "}"
        "QListWidget::item {"
        "  padding: 12px 12px;"
        "  border-bottom: 1px solid rgba(255,255,255,0.04);"
        "}"
        "QListWidget::item:selected {"
        "  background: rgba(106,88,255,0.24);"
        "}");

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(16, 16, 16, 16);
    layout->setSpacing(10);

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