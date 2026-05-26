r"""
SpellVision — Pass 7d.3 add button click fix.

DIAGNOSTIC DATA CONFIRMED:
  - addButton_ receives MousePress + MouseRelease events (from eventFilter)
  - QPushButton::clicked signal does NOT fire (no LAMBDA log, no onAddStageClicked log)

ROOT CAUSE HYPOTHESIS:
  The addBtnStyle stylesheet uses `border: none` + `padding: 0 12px` +
  `:hover` and `:pressed` pseudo-states. This combination is known to
  cause QPushButton::clicked to not fire on some Qt+Windows configs
  because the stylesheet rendering machinery interferes with the
  internal click detection (which checks if press AND release happened
  in the "interactive" region of the button).

FIX:
  Rewrite addBtnStyle to:
  - Use `border-width: 0` (or omit border entirely) instead of `border: none`
  - Use `min-width` instead of fixed padding for sizing
  - Keep visual appearance equivalent

If this doesn't fix it, the next step is removing the stylesheet
entirely from the button to confirm Qt fires clicked normally
without any stylesheet, then re-adding styles incrementally to find
the specific rule that breaks it.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

MARKER = "PASS 7D3 BUTTON CLICK FIX"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


# Replace the entire addBtnStyle function. This is the cleanest fix —
# rather than tweak the existing stylesheet incrementally, replace it
# with a minimal version that's known to work for button click events.

NEW_ADDBTN_STYLE = '''QString addBtnStyle(bool enabled)
{
    // --- ''' + MARKER + ''' ---
    // Stripped to minimum CSS that doesn't interfere with click hit-
    // testing. The previous version had `border: none` + padding +
    // hover/pressed pseudos which caused QPushButton::clicked to not
    // fire on Windows even when MouseButtonPress/Release events were
    // delivered. This minimal version still gives the accent-fill
    // visual without breaking the click signal.
    const auto &tm = ThemeManager::instance();
    if (!enabled)
    {
        return QStringLiteral(
            "QPushButton { "
            "  background-color: %1; "
            "  color: %2; "
            "  border-width: 0px; "
            "  border-radius: %3px; "
            "  font-size: 13px; "
            "  font-weight: 800; "
            "}"
        ).arg(tm.background0Color().name(),
              tm.textMutedColor().name(),
              QString::number(tm.radiusControl()));
    }
    return QStringLiteral(
        "QPushButton { "
        "  background-color: %1; "
        "  color: %2; "
        "  border-width: 0px; "
        "  border-radius: %3px; "
        "  font-size: 13px; "
        "  font-weight: 800; "
        "}"
        "QPushButton:hover { background-color: %4; }"
    ).arg(tm.accentColor().name(),
          tm.background0Color().name(),
          QString::number(tm.radiusControl()),
          tm.accentColor().lighter(110).name());
}'''


def main() -> int:
    project = Path(__file__).resolve().parent
    path = project / "qt_ui" / "chain" / "ChainDialogBarWidget.cpp"
    if not path.exists():
        print(f"  Not found: {path}")
        return 1

    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"  Already patched: {path.name}")
        return 0

    backup_once(path, ".pre_pass7d3_button_click_fix.bak")

    # Match the entire addBtnStyle function (signature + body).
    # The function uses an if/return + return pattern, so we need to
    # match from the signature through the matching closing brace.
    # Use a manual brace-balance approach since this is complex.
    sig = "QString addBtnStyle(bool enabled)"
    sig_idx = text.find(sig)
    if sig_idx == -1:
        raise RuntimeError("Cannot find addBtnStyle function signature")

    # Find the opening brace after the signature
    brace_idx = text.find("{", sig_idx)
    if brace_idx == -1:
        raise RuntimeError("Cannot find opening brace of addBtnStyle")

    # Walk forward, counting braces, to find the matching close brace
    depth = 0
    end_idx = -1
    for i in range(brace_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break
    if end_idx == -1:
        raise RuntimeError("Cannot find closing brace of addBtnStyle")

    # Replace [sig_idx : end_idx+1] with the new function
    new_text = text[:sig_idx] + NEW_ADDBTN_STYLE + text[end_idx + 1:]

    # Convert to CRLF if needed (project convention)
    new_text = new_text.replace("\r\n", "\n").replace("\n", "\r\n")

    path.write_bytes(new_text.encode("utf-8"))
    print(f"  Patched: {path.name}")
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("After rebuild and clicking + add stage button, you should see:")
    print("  [ChainStudio] LAMBDA: addButton_ clicked signal received...")
    print("  [ChainStudio] DialogBar::onAddStageClicked fired")
    print("  [ChainStudio] Page::onRailAddStageRequested pos: QPoint(...)")
    print("  [ChainStudio] Page::showAddStageMenu pos: ...")
    print("  ... and the menu should pop")
    print()
    print("If the LAMBDA and onAddStageClicked log lines now appear but")
    print("the menu still doesn't pop, the menu.exec is the remaining")
    print("issue — that points to the LeftRailScrollAreaWindow error")
    print("being related to QMenu parent window. We can address that")
    print("by changing 'QMenu menu(this)' to 'QMenu menu(window())' in")
    print("ChainStudioPage::showAddStageMenu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
