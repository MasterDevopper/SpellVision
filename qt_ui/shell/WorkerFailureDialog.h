#pragma once

#include <QString>

class QWidget;

namespace spellvision::shell
{

// A worker or subprocess failed. `body` is the curated sentence a person reads; `stderrText` is
// whatever the process printed -- usually a Python traceback -- and goes behind Qt's own
// "Show Details..." (setDetailedText), still readable and copyable, never the body.
//
// One function for every page. The first version was private to WorkflowLibraryPage, and the
// tree-wide test then found three more sites in two files doing the same thing by hand.
void showWorkerFailure(QWidget *parent, const QString &title, const QString &body, const QString &stderrText);

} // namespace spellvision::shell
