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
// The sweep rule `shell-geometry-through-the-layout` is the other half: outside this package,
// nothing may measure the rail. Inside it, this is where the measurement is turned into a rect.

// The drawer never gets shorter than this, whatever the preference says -- below it the queue table
// has no rows and the tab bar is the whole panel.
inline constexpr int kDrawerMinimumHeight = 160;
// And it never eats the last of the page: this much of the content area always stays visible above
// it, so the drawer reads as an overlay rather than as a new bottom half of the window.
inline constexpr int kDrawerPageRemainder = 32;

// Where the activity drawer goes, given where PAGE CONTENT BEGINS.
//
// `contentOrigin` is SideRail::contentOrigin() -- (railWidth, 0) for a vertical rail, (0,
// railHeight) for a horizontal one, and (0, 0) for a rail the shell has hidden. The caller decides
// what a hidden rail means, because contentOrigin() is pure geometry and a hidden widget keeps its
// geometry; see MainWindow::positionQueueOverlay for why that guard is not redundant.
//
// The drawer is bottom-anchored and spans from the origin's x to the shell's right edge. Its
// ceiling is what the rail leaves BELOW itself -- with a vertical rail origin.y() is 0 and the
// number is what it always was, and with a horizontal rail the drawer stops short of covering it.
inline QRect drawerRect(const QPoint &contentOrigin, const QSize &shell, int preferredHeight)
{
    const int ceiling =
        std::max(kDrawerMinimumHeight, shell.height() - contentOrigin.y() - kDrawerPageRemainder);
    const int height = std::clamp(preferredHeight, kDrawerMinimumHeight, ceiling);
    const int width = std::max(0, shell.width() - contentOrigin.x());
    return QRect(contentOrigin.x(), shell.height() - height, width, height);
}

} // namespace spellvision::shell
