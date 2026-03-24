#pragma once

#include <QDialog>
#include <QStringList>

class QListWidget;
class QListWidgetItem;
class QLineEdit;

class CommandPaletteDialog : public QDialog
{
    Q_OBJECT

public:
    explicit CommandPaletteDialog(QWidget *parent = nullptr);

    void setCommands(const QStringList &commands);

signals:
    void commandTriggered(const QString &command);

private slots:
    void filterCommands(const QString &text);
    void activateCurrent();
    void activateItem(QListWidgetItem *item);

private:
    void updateResults(const QString &query);

    QLineEdit *searchBox_ = nullptr;
    QListWidget *resultsList_ = nullptr;
    QStringList allCommands_;
};