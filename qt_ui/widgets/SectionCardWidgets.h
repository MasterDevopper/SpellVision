#pragma once

#include <QString>

class QLabel;
class QFrame;
class QVBoxLayout;
class QWidget;

namespace spellvision::widgets
{

QFrame *createCard(const QString &objectName = QString(), QWidget *parent = nullptr);
QLabel *createSectionTitle(const QString &text, QWidget *parent = nullptr);
QLabel *createSectionBody(const QString &text, QWidget *parent = nullptr);
void repolishWidget(QWidget *widget);
QWidget *makeCollapsibleSection(QVBoxLayout *parentLayout,
                                const QString &title,
                                QWidget *body,
                                bool expanded = true);

} // namespace spellvision::widgets
