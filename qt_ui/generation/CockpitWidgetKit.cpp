#include "generation/CockpitWidgetKit.h"

#include <QAbstractItemView>
#include <QAbstractSpinBox>
#include <QColor>
#include <QSignalBlocker>
#include <QSizePolicy>

namespace spellvision::generation
{

QString comboStoredValue(const QComboBox *combo)
{
    if (!combo)
        return {};
    const QString dataValue = combo->currentData(Qt::UserRole).toString().trimmed();
    if (!dataValue.isEmpty())
        return dataValue;
    return combo->currentText().trimmed();
}

QString comboDisplayValue(const QComboBox *combo)
{
    return combo ? combo->currentText().trimmed() : QString();
}

QString normalizedVideoStackModeToken(const QString &value)
{
    const QString token = value.trimmed().toLower();
    if (token.isEmpty() || token == QStringLiteral("auto") || token == QStringLiteral("auto_detect"))
        return QStringLiteral("auto");
    if (token.contains(QStringLiteral("wan")) || token.contains(QStringLiteral("dual"))
        || token.contains(QStringLiteral("high_noise")) || token.contains(QStringLiteral("low_noise")))
        return QStringLiteral("wan_dual_noise");
    if (token.contains(QStringLiteral("single")))
        return QStringLiteral("single_model");
    return token;
}

void populateComboFromCatalog(QComboBox *combo,
                              const QVector<spellvision::assets::CatalogEntry> &entries,
                              const QStringList &fallbackItems)
{
    if (!combo)
        return;
    const QString priorValue = comboStoredValue(combo);
    const QSignalBlocker blocker(combo);
    combo->clear();
    for (const auto &entry : entries)
        combo->addItem(entry.display, entry.value);
    if (combo->count() == 0)
    {
        for (const QString &fallback : fallbackItems)
            combo->addItem(fallback, fallback);
    }
    if (!priorValue.isEmpty())
    {
        for (int index = 0; index < combo->count(); ++index)
        {
            if (combo->itemData(index, Qt::UserRole).toString().compare(priorValue, Qt::CaseInsensitive) == 0
                || combo->itemText(index).compare(priorValue, Qt::CaseInsensitive) == 0)
            {
                combo->setCurrentIndex(index);
                return;
            }
        }
        if (combo->isEditable())
            combo->setEditText(priorValue);
    }
    else if (combo->count() > 0)
    {
        combo->setCurrentIndex(0);
    }
}

bool selectComboByContains(QComboBox *combo, const QStringList &needles)
{
    if (!combo)
        return false;
    for (int index = 0; index < combo->count(); ++index)
    {
        const QString haystack = (combo->itemText(index) + QLatin1Char(' ')
                                  + combo->itemData(index, Qt::UserRole).toString())
                                     .toLower();
        for (const QString &needle : needles)
        {
            if (!needle.trimmed().isEmpty() && haystack.contains(needle.toLower()))
            {
                combo->setCurrentIndex(index);
                return true;
            }
        }
    }
    return false;
}

void configureComboBox(QComboBox *combo)
{
    if (!combo)
        return;
    combo->setFocusPolicy(Qt::StrongFocus);
    combo->setMaxVisibleItems(18);
    combo->setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
    combo->setMinimumContentsLength(10);
    combo->setMinimumWidth(0);
    combo->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    if (combo->view())
    {
        combo->view()->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
        combo->view()->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        combo->view()->setTextElideMode(Qt::ElideMiddle);
    }
}

void configureSpinBox(QSpinBox *spin)
{
    if (!spin)
        return;
    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

void configureDoubleSpinBox(QDoubleSpinBox *spin)
{
    if (!spin)
        return;
    spin->setAccelerated(true);
    spin->setKeyboardTracking(false);
    spin->setButtonSymbols(QAbstractSpinBox::UpDownArrows);
    spin->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    spin->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

QString rgbaToken(ThemeManager::Color c, qreal alpha)
{
    const QColor k = ThemeManager::instance().color(c);
    return QStringLiteral("rgba(%1,%2,%3,%4)")
        .arg(k.red())
        .arg(k.green())
        .arg(k.blue())
        .arg(alpha, 0, 'f', 2);
}

} // namespace spellvision::generation
