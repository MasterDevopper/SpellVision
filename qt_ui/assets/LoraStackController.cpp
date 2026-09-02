#include "LoraStackController.h"
#include "../ThemeManager.h"

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
            rowLayout->setContentsMargins(ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug), ThemeManager::instance().spacing(ThemeManager::Spacing::Snug));
            rowLayout->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));

            const int tight = ThemeManager::instance().spacing(ThemeManager::Spacing::Tight);

            auto *topRow = new QHBoxLayout;
            topRow->setContentsMargins(0, 0, 0, 0);
            topRow->setSpacing(tight);

            // No caption: at a half-screen window the name row is ~190px, and "Enabled" + a name +
            // the two reorder arrows squeezed the caption to "Enal". A bare box beside a name is
            // the convention every LoRA stack UI uses; the word lives in the tooltip and the
            // accessible name so it is still said, not shown.
            auto *enabledBox = new QCheckBox(row);
            enabledBox->setChecked(entry.enabled);
            enabledBox->setToolTip(QStringLiteral("Enabled"));
            enabledBox->setAccessibleName(QStringLiteral("Enabled"));

            // Name only (the full path is a tooltip). Showing display + path here made the label a tall
            // wrapped block in the narrow inspector.
            auto *title = new QLabel(entry.display, row);
            title->setObjectName(QStringLiteral("SectionBody"));
            title->setWordWrap(true);
            title->setToolTip(entry.value);

            topRow->addWidget(enabledBox);
            topRow->addWidget(title, 1);
            rowLayout->addLayout(topRow);

            // Buttons on their OWN row. Packed inline with the name they overflowed the ~320px-wide
            // inspector (Down clipped to "Do", Remove off-screen) — the reported right-panel clip.
            // Two rows share the ~215px this card gets at a half-screen window: Change + Remove
            // here, the reorder arrows beside the weight spinner below. Four full-word buttons in
            // one row still clipped to "hang" / "low" / "mo" at every window under 1600px wide --
            // the row had moved off the name line but not into the width it actually gets.
            auto *buttonRow = new QHBoxLayout;
            buttonRow->setContentsMargins(0, 0, 0, 0);
            buttonRow->setSpacing(tight);
            auto *editButton = new QPushButton(QStringLiteral("Change"), row);
            editButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            auto *removeButton = new QPushButton(QStringLiteral("Remove"), row);
            removeButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            buttonRow->addWidget(editButton);
            buttonRow->addWidget(removeButton);
            buttonRow->addStretch(1);
            rowLayout->addLayout(buttonRow);

            auto *weightRow = new QHBoxLayout;
            weightRow->setContentsMargins(0, 0, 0, 0);
            weightRow->setSpacing(ThemeManager::instance().spacing(ThemeManager::Spacing::Tight));
            auto *weightLabel = new QLabel(QStringLiteral("Weight"), row);
            auto *weightSpin = new QDoubleSpinBox(row);
            weightSpin->setDecimals(2);
            weightSpin->setSingleStep(0.05);
            weightSpin->setRange(0.0, 2.0);
            weightSpin->setValue(entry.weight);
            weightSpin->setButtonSymbols(QAbstractSpinBox::PlusMinus);
            weightSpin->setKeyboardTracking(false);
            // Reorder arrows sit at the end of the NAME row: the wrapping name label yields width,
            // so two 32px glyph buttons fit at any card width, and it is where reorder lives in
            // every list a user has met.
            auto *upButton = new QPushButton(QStringLiteral("▲"), row);
            upButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            upButton->setToolTip(QStringLiteral("Move up in the stack"));
            upButton->setFixedWidth(32);
            upButton->setEnabled(index > 0);
            auto *downButton = new QPushButton(QStringLiteral("▼"), row);
            downButton->setObjectName(QStringLiteral("TertiaryActionButton"));
            downButton->setToolTip(QStringLiteral("Move down in the stack"));
            downButton->setFixedWidth(32);
            downButton->setEnabled(index + 1 < stack_->size());
            topRow->addWidget(upButton);
            topRow->addWidget(downButton);
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
