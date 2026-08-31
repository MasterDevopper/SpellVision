#pragma once

#include <QJsonObject>
#include <QString>

namespace spellvision::workers
{

// Every generation request the app sends is assembled here.
//
// These three functions were private members of MainWindow, which meant the 320 lines that decide
// what the worker actually receives -- which command it dispatches on, which keys carry the model,
// what a missing steps/cfg/seed/strength becomes -- could only be exercised by launching the GUI
// and rendering something. They touch no MainWindow state; they are functions of their arguments
// that happened to be declared inside a QMainWindow. Moving them out is what makes them testable,
// and the tests are the point of the move.
//
// The project root is a PARAMETER rather than a call to the resolver. The behaviour is identical
// -- the caller passes what the resolver returns -- but a test can point it at a fixture directory
// instead of the machine it is running on.

// The worker's task command for a cockpit mode id. Returns an empty string for a mode that is not
// a generation mode, which is how callers tell the difference.
QString workerTaskCommandForMode(const QString &modeId);

// The enqueue request for a cockpit generation.
//
// NOTE this has SIDE EFFECTS despite its name: it creates the output directory, and for a
// filename beginning "plate" it writes prompt.txt beside the output. Both predate the extraction
// and are preserved exactly; they are called out here because "build" reads as pure and this is
// not, and a caller that builds a request to inspect it will touch the disk.
QJsonObject buildWorkerGenerationRequest(const QString &modeId,
                                         const QJsonObject &payload,
                                         const QString &projectRoot);

// The enqueue request for launching an imported ComfyUI workflow profile.
// Also creates its output directory.
QJsonObject buildWorkflowLaunchRequest(const QJsonObject &profile,
                                       const QString &modelOverride,
                                       const QString &loraOverride,
                                       const QString &loraScaleOverride,
                                       const QString &projectRoot,
                                       const QString &managedComfyRoot);

}  // namespace spellvision::workers
