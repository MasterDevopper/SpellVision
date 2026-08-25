#pragma once

#include "ThemeManager.h"
#include "assets/AssetCatalogScanner.h"

#include <QComboBox>
#include <QDoubleSpinBox>
#include <QSpinBox>
#include <QString>
#include <QStringList>
#include <QVector>

namespace spellvision::generation
{

QString comboStoredValue(const QComboBox *combo);
QString comboDisplayValue(const QComboBox *combo);
QString normalizedVideoStackModeToken(const QString &value);
void populateComboFromCatalog(QComboBox *combo,
                              const QVector<spellvision::assets::CatalogEntry> &entries,
                              const QStringList &fallbackItems = {});
bool selectComboByContains(QComboBox *combo, const QStringList &needles);
void configureComboBox(QComboBox *combo);
void configureSpinBox(QSpinBox *spin);
void configureDoubleSpinBox(QDoubleSpinBox *spin);
QString rgbaToken(ThemeManager::Color c, qreal alpha);

} // namespace spellvision::generation
