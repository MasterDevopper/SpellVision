#pragma once

#include "style/SvStyle.h"

#include <QString>

class QFrame;
class QPushButton;
class QToolButton;
class QWidget;

namespace spellvision::kit
{

// Factories that say what a widget IS. Each sets the role or surface property SvStyle reads and
// keeps the object name the caller asks for, because object names are load-bearing (UI Automation,
// the responsive matrix, eleven pytest ratchets). No layouts, no copy, no page knowledge here.
QPushButton *button(style::Role role, const QString &text, const QString &objectName, QWidget *parent = nullptr);
QToolButton *chip(const QString &text, const QString &objectName, QWidget *parent = nullptr); // checkable
QFrame *card(style::Surface surface, const QString &objectName, QWidget *parent = nullptr);   // StyledPanel
QWidget *row(const QString &label, QWidget *control, QWidget *parent = nullptr);              // label left, control right, hairline below

// For widgets that already exist. Re-polishes so the change paints immediately.
void setRole(QWidget *widget, style::Role role);
void setSurface(QFrame *frame, style::Surface surface);

} // namespace spellvision::kit
