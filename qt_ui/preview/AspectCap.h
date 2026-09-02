#pragma once

#include <QSize>

class QWidget;

namespace spellvision::preview
{

// Bound `capWidget` to the aspect of what it shows. `content` is the widget the media is painted
// into (a QLabel inside `capWidget`); `fittedContent` is the size that media currently occupies.
// The cap is fitted + the chrome between the two widgets, so the box hugs the picture and the
// empty mat around a portrait render in a wide column -- or a wide clip in a tall one -- goes away.
//
// Why a maximum size and not a size hint: layouts honour maximumSize strictly, so the freed space
// returns to the column and the picture sits centred; a hint is advisory and Expanding wins.
//
// Fixed point: a box that already fits the aspect re-fits to itself, so applying this on every
// refit converges in one step and never oscillates. It only ever loosens when releaseAspectCap is
// called -- which the controllers do when the PARENT resizes (so the picture grows with the window)
// and whenever the preview is cleared or the stack changes page (so an image cap never squeezes a
// video). Skips changes within 1px so rounding cannot flap it.
void applyAspectCap(QWidget *capWidget, const QWidget *content, const QSize &fittedContent);
void releaseAspectCap(QWidget *capWidget);

} // namespace spellvision::preview
