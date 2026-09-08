#pragma once

#include <QPoint>
#include <QRect>
#include <QSize>

#include <algorithm>

namespace spellvision::shell
{

// Shell-level furniture that is POSITIONED rather than laid out. There is one such thing today --
// the activity drawer, a free child of centralShell_ (spec
// docs/superpowers/specs/2026-09-08-shell-layouts-design.md, sections 2.3 and 2.5) -- and it is the
// reason this header exists rather than the maths staying where it was.
//
// MainWindow::positionQueueOverlay used to compute the drawer's rect itself, starting its X at
// sideRail_->width(). That was correct for exactly as long as the rail was a left-hand vertical
// strip: an assumption nothing in the code stated, nothing enforced, and no test could see, because
// the arithmetic lived in a private method of a window too heavy to instantiate. Moving the
// decision here makes it a pure function of two points and a preference, which is a thing a test
// can turn on its side.
//
// EVERY decision about the drawer's rect lives here, including what a hidden rail means. That one
// arrived second, and the reason it moved is worth keeping: while MainWindow pre-zeroed the origin
// itself, deleting the visibility test compiled, passed ctest, passed pytest and passed the sweep
// rule, and left the drawer inset over empty page -- a defect only a screenshot could see. A
// decision that only a screenshot can check is a decision someone will delete as redundant, and
// this one LOOKS redundant. So MainWindow now passes two facts it can observe and makes no
// judgement, and the judgement sits where three tests already are.
//
// The sweep rule `shell-geometry-through-the-layout` is the other half: outside this package,
// nothing may measure the rail. Inside it, this is where the measurement is turned into a rect.

// The drawer never gets shorter than this, whatever the preference says -- below it the queue table
// has no rows and the tab bar is the whole panel.
inline constexpr int kDrawerMinimumHeight = 160;
// And it never eats the last of the page: this much of the content area always stays visible above
// it, so the drawer reads as an overlay rather than as a new bottom half of the window.
inline constexpr int kDrawerPageRemainder = 32;

// Where the activity drawer goes, given where PAGE CONTENT BEGINS and whether the rail is showing.
//
// `railOrigin` is SideRail::contentOrigin() -- (railWidth, 0) for a vertical rail and
// (0, railHeight) for a horizontal one. It is PURELY GEOMETRIC by design (see SideRail.h): a rail
// that has never been shown must still report a real origin, or every test of it would read zero.
//
// `railVisible` is therefore a SEPARATE fact, and it is not redundant however geometric the origin
// looks. A HIDDEN WIDGET KEEPS ITS GEOMETRY -- togglePrimarySidebar() only calls setVisible(false),
// so a collapsed rail still measures 64 px wide and still reports an origin of (64, 0). Take the
// origin without this test and the drawer stays inset by 64 px over empty page every time the user
// collapses the rail. Hidden means the content area starts at the shell's own corner, so the origin
// is discarded rather than trusted.
//
// The drawer is bottom-anchored and spans from that corner to the shell's right edge. Its ceiling is
// what the rail leaves BELOW itself -- with a vertical rail the y is 0 and the number is what it
// always was, and with a horizontal rail the drawer stops short of covering it.
inline QRect drawerRect(const QPoint &railOrigin,
                        bool railVisible,
                        const QSize &shell,
                        int preferredHeight)
{
    const QPoint origin = railVisible ? railOrigin : QPoint(0, 0);
    const int ceiling =
        std::max(kDrawerMinimumHeight, shell.height() - origin.y() - kDrawerPageRemainder);
    const int height = std::clamp(preferredHeight, kDrawerMinimumHeight, ceiling);
    const int width = std::max(0, shell.width() - origin.x());
    return QRect(origin.x(), shell.height() - height, width, height);
}

} // namespace spellvision::shell
