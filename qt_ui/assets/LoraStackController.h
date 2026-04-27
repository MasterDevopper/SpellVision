#pragma once

#include "ModelStackState.h"

#include <QVector>
#include <QString>

#include <functional>

class QObject;
class QBoxLayout;
class QLabel;
class QPushButton;
class QWidget;

namespace spellvision::assets
{

struct LoraStackBindings
{
    QWidget *container = nullptr;
    QBoxLayout *layout = nullptr;
    QLabel *summaryLabel = nullptr;
    QPushButton *clearButton = nullptr;
};

class LoraStackController final
{
public:
    explicit LoraStackController(QObject *owner = nullptr);

    void bind(QVector<LoraStackEntry> *stack, const LoraStackBindings &bindings);
    void setDisplayResolver(std::function<QString(const QString &)> resolver);
    void setChangedCallback(std::function<void()> callback);
    void setReplaceRequestedCallback(std::function<void(int)> callback);

    void rebuild();
    void clear();
    void addOrUpdate(const QString &value, const QString &display, double weight = 1.0, bool enabled = true);
    bool replaceAt(int index, const QString &value, const QString &display);

    QString firstEnabledValue() const;
    int enabledCount() const;
    const QVector<LoraStackEntry> &stack() const;

private:
    void emitChanged();
    QString displayFor(const LoraStackEntry &entry) const;
    void clearLayout();
    bool hasValidIndex(int index) const;

    QObject *owner_ = nullptr;
    QVector<LoraStackEntry> *stack_ = nullptr;
    LoraStackBindings bindings_;
    std::function<QString(const QString &)> displayResolver_;
    std::function<void()> changedCallback_;
    std::function<void(int)> replaceRequestedCallback_;
    QVector<LoraStackEntry> emptyStack_;
};

} // namespace spellvision::assets
