#include "LoraStackController.h"

#include <QAbstractSpinBox>
#include <QBoxLayout>
#include <QCheckBox>
#include <QDoubleSpinBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QLayoutItem>
#include <QPushButton>
#include <QVBoxLayout>
#include <QWidget>

namespace spellvision::assets
{

LoraStackController::LoraStackController(QObject *owner)
    : owner_(owner)
{
}

void LoraStackController::bind(QVector<LoraStackEntry> *stack, const LoraStackBindings &bindings)
{
    stack_ = stack;
    bindings_ = bindings;
    rebuild();
}

void LoraStackController::setDisplayResolver(std::function<QString(const QString &)> resolver)
{
    displayResolver_ = std::move(resolver);
}

void LoraStackController::setChangedCallback(std::function<void()> callback)
{
    changedCallback_ = std::move(callback);
}

void LoraStackController::setReplaceRequestedCallback(std::function<void(int)> callback)
{
    replaceRequestedCallback_ = std::move(callback);
}

void LoraStackController::rebuild()
{
    if (!bindings_.layout)
        return;

    clearLayout();

    if (!stack_ || stack_->isEmpty())
    {
        if (bindings_.container)
        {
            auto *empty = new QLabel(QStringLiteral("No LoRAs selected. Add one or more LoRAs to build a reusable stack."), bindings_.container);
            empty->setObjectName(QStringLiteral("ImageGenHint"));
            empty->setWordWrap(true);
            bindings_.layout->addWidget(empty);
        }
    }
    else
    {
        for (int index = 0; index < stack_->size(); ++index)
        {
            LoraStackEntry &entry = (*stack_)[index];
            if (entry.display.trimmed().isEmpty())
                entry.display = displayFor(entry);

            auto *row = new QFrame(bindings_.container);
            row->setObjectName(QStringLiteral("InputDropCard"));
            auto *rowLayout = new QVBoxLayout(row);
            rowLayout->setContentsMargins(10, 10, 10, 10);
            rowLayout->setSpacing(8);

            auto *topRow = new QHBoxLayout;
            topRow->setContentsMargins(0, 0, 0, 0);
            topRow->setSpacing(8);

            auto *enabledBox = new QCheckBox(QStringLiteral("Enabled"), row);
            enabledBox->setChecked(entry.enabled);

            auto *title = new QLabel(QStringLiteral("%1\n%2").arg(entry.display, entry.value), row);
            title->setObjectName(QStringLiteral("SectionBody"));
            title->setWordWrap(true);

            auto *editButton = new QPushButton(QStringLiteral("Change"), row);
            editButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            auto *upButton = new QPushButton(QStringLiteral("Up"), row);
            upButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            auto *downButton = new QPushButton(QStringLiteral("Down"), row);
            downButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            auto *removeButton = new QPushButton(QStringLiteral("Remove"), row);
            removeButton->setObjectName(QStringLiteral("TertiaryActionButton"));

            topRow->addWidget(enabledBox);
            topRow->addWidget(title, 1);
            topRow->addWidget(editButton);
            topRow->addWidget(upButton);
            topRow->addWidget(downButton);
            topRow->addWidget(removeButton);
            rowLayout->addLayout(topRow);

            auto *weightRow = new QHBoxLayout;
            weightRow->setContentsMargins(0, 0, 0, 0);
            weightRow->setSpacing(8);
            auto *weightLabel = new QLabel(QStringLiteral("Weight"), row);
            auto *weightSpin = new QDoubleSpinBox(row);
            weightSpin->setDecimals(2);
            weightSpin->setSingleStep(0.05);
            weightSpin->setRange(0.0, 2.0);
            weightSpin->setValue(entry.weight);
            weightSpin->setButtonSymbols(QAbstractSpinBox::PlusMinus);
            weightSpin->setKeyboardTracking(false);
            weightRow->addWidget(weightLabel);
            weightRow->addWidget(weightSpin, 1);
            rowLayout->addLayout(weightRow);

            QObject::connect(enabledBox, &QCheckBox::toggled, row, [this, index](bool checked) {
                if (!hasValidIndex(index))
                    return;
                (*stack_)[index].enabled = checked;
                rebuild();
                emitChanged();
            });

            QObject::connect(weightSpin, qOverload<double>(&QDoubleSpinBox::valueChanged), row, [this, index](double value) {
                if (!hasValidIndex(index))
                    return;
                (*stack_)[index].weight = value;
                emitChanged();
            });

            QObject::connect(editButton, &QPushButton::clicked, row, [this, index]() {
                if (!hasValidIndex(index))
                    return;
                if (replaceRequestedCallback_)
                    replaceRequestedCallback_(index);
            });

            QObject::connect(removeButton, &QPushButton::clicked, row, [this, index]() {
                if (!hasValidIndex(index))
                    return;
                stack_->removeAt(index);
                rebuild();
                emitChanged();
            });

            QObject::connect(upButton, &QPushButton::clicked, row, [this, index]() {
                if (!hasValidIndex(index) || index <= 0)
                    return;
                stack_->swapItemsAt(index, index - 1);
                rebuild();
                emitChanged();
            });

            QObject::connect(downButton, &QPushButton::clicked, row, [this, index]() {
                if (!hasValidIndex(index) || index >= stack_->size() - 1)
                    return;
                stack_->swapItemsAt(index, index + 1);
                rebuild();
                emitChanged();
            });

            bindings_.layout->addWidget(row);
        }
    }

    bindings_.layout->addStretch(1);

    if (bindings_.summaryLabel)
        bindings_.summaryLabel->setText(ModelStackState::summaryText(stack_ ? *stack_ : emptyStack_));
    if (bindings_.clearButton)
        bindings_.clearButton->setEnabled(stack_ && !stack_->isEmpty());
}

void LoraStackController::clear()
{
    if (!stack_)
        return;
    if (stack_->isEmpty())
    {
        rebuild();
        return;
    }

    stack_->clear();
    rebuild();
    emitChanged();
}

void LoraStackController::addOrUpdate(const QString &value, const QString &display, double weight, bool enabled)
{
    if (!stack_)
        return;

    const QString normalized = ModelStackState::normalizedPath(value);
    if (normalized.isEmpty())
        return;

    LoraStackEntry entry;
    entry.value = normalized;
    entry.display = display.trimmed().isEmpty() ? displayFor(entry) : display.trimmed();
    entry.weight = weight;
    entry.enabled = enabled;

    ModelStackState::upsertLora(*stack_, entry);
    rebuild();
    emitChanged();
}

bool LoraStackController::replaceAt(int index, const QString &value, const QString &display)
{
    if (!hasValidIndex(index))
        return false;

    const QString normalized = ModelStackState::normalizedPath(value);
    if (normalized.isEmpty())
        return false;

    (*stack_)[index].value = normalized;
    (*stack_)[index].display = display.trimmed().isEmpty() ? displayFor((*stack_)[index]) : display.trimmed();
    rebuild();
    emitChanged();
    return true;
}

QString LoraStackController::firstEnabledValue() const
{
    return ModelStackState::firstEnabledLoraValue(stack_ ? *stack_ : emptyStack_);
}

int LoraStackController::enabledCount() const
{
    return ModelStackState::enabledLoraCount(stack_ ? *stack_ : emptyStack_);
}

const QVector<LoraStackEntry> &LoraStackController::stack() const
{
    return stack_ ? *stack_ : emptyStack_;
}

void LoraStackController::emitChanged()
{
    if (changedCallback_)
        changedCallback_();
}

QString LoraStackController::displayFor(const LoraStackEntry &entry) const
{
    const QString value = ModelStackState::normalizedPath(entry.value);
    if (value.isEmpty())
        return QString();

    if (displayResolver_)
    {
        const QString resolved = displayResolver_(value).trimmed();
        if (!resolved.isEmpty())
            return resolved;
    }

    return value.section('/', -1).section('\\', -1);
}

void LoraStackController::clearLayout()
{
    if (!bindings_.layout)
        return;

    while (QLayoutItem *item = bindings_.layout->takeAt(0))
    {
        if (QWidget *widget = item->widget())
            widget->deleteLater();
        delete item;
    }
}

bool LoraStackController::hasValidIndex(int index) const
{
    return stack_ && index >= 0 && index < stack_->size();
}

} // namespace spellvision::assets
