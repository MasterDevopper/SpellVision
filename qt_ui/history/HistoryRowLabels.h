#pragma once

#include <QString>

// What a history row says in its mode-dependent columns.
//
// History v1 flattened image results onto a video-shaped row, so the UI stuffed an image's step
// count into the Duration column and a T2I render read as "35 frames". Schema v2 fixed the RECORD
// (python/history_schema.py: a stable core plus a mode_payload keyed by media type) and the page was
// taught to branch -- but the RULE for what each column says then existed twice: once in
// `history_schema.detail_label`, which had no production caller and only its own test, and once
// hand-rolled inline in T2VHistoryPage. Two implementations, one tested and unused, one used and
// untested, agreeing only by coincidence.
//
// The rule belongs here, in the layer that renders it, with one test.
namespace spellvision::history
{

// Column 2. Video says how long it is; an image says how many steps made it. Never the other way
// round -- borrowing Duration for steps is the original defect.
QString detailLabel(bool isImage, const QString &mode, const QString &imageSteps,
                    const QString &durationLabel);

// Column 4. Video says which model stack ran; an image says which checkpoint did. A video without a
// resolved stack summary is still a video, so it says so rather than going blank.
QString stackLabel(bool isImage, const QString &modelName, const QString &stackSummary);

} // namespace spellvision::history
