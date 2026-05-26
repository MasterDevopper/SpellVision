r"""
SpellVision — Pass 7d.3 hitButton diagnostic.

AUTHORITATIVE Qt source (qabstractbutton.cpp) reveals the exact mechanism:

  void QAbstractButton::mousePressEvent(QMouseEvent *e) {
      if (e->button() != Qt::LeftButton) { e->ignore(); return; }
      if (hitButton(e->pos())) {          // <-- this must be TRUE
          setDown(true);                   // sets d->down = true
          d->emitPressed();
          e->accept();
      } else {
          e->ignore();                     // d->down stays false
      }
  }

  void QAbstractButton::mouseReleaseEvent(QMouseEvent *e) {
      d->pressed = false;
      if (e->button() != Qt::LeftButton) { e->ignore(); return; }
      if (!d->down) {                      // <-- if not down, no click
          e->ignore();
          return;
      }
      if (hitButton(e->pos())) {
          d->repeatTimer.stop();
          d->click();                      // <-- THIS emits released() AND clicked()
          e->accept();
      } else {
          setDown(false);
          e->ignore();
      }
  }

  bool QAbstractButton::hitButton(const QPoint &pos) const {
      return rect().contains(pos);
  }

Our event filter shows Press+Release arriving at addButton_, but clicked
never fires. The ONLY explanation consistent with the Qt source is that
EITHER hitButton(e->pos()) returns false on press (so d->down never goes
true), OR something between press and release resets d->down.

To find out which, log:
  - e->pos() (local position of the event)
  - addButton_->rect() (button's geometry)
  - addButton_->isDown() (the d->down flag) AFTER the press has been processed

This determines the exact failure mode with no more guessing.
"""

from __future__ import annotations
import re
import sys
from pathlib import Path

MARKER = "PASS 7D3 HITBUTTON DIAGNOSTIC"


def backup_once(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists() and path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  Backup written: {backup.name}")


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

    backup_once(path, ".pre_pass7d3_hitbutton_diag.bak")

    # Find the existing addButton_ event log block in eventFilter and
    # replace its body with a richer diagnostic that captures position,
    # rect, hitButton result, and isDown state.

    # First, find the eventFilter function opening
    ef_pattern = re.compile(
        r"(bool ChainDialogBarWidget::eventFilter\(QObject \*watched, QEvent \*event\)\s*\r?\n\{\s*\r?\n)"
    )
    ef_match = ef_pattern.search(text)
    if not ef_match:
        raise RuntimeError("Cannot find eventFilter function")

    # Remove any existing addButton_ blocks (from prior diagnostics)
    # Match the simple "if (watched == addButton_)" diagnostic block
    # added by aggressive_diag_v2, which spans a few lines and ends
    # with two closing braces on their own lines.
    text = re.sub(
        r"\s*// --- PASS 7D3 AGGRESSIVE DIAGNOSTIC V2: log all events targeting addButton_ ---[\s\S]*?if \(watched == addButton_\)[\s\S]*?\}\s*\r?\n\s*\}\s*\r?\n",
        "\r\n",
        text,
    )
    # Also remove any previous eventfilter workaround block
    text = re.sub(
        r"\s*// --- PASS 7D3 EVENTFILTER WORKAROUND[\s\S]*?if \(watched == addButton_ &&[\s\S]*?\}\s*\r?\n\s*\}\s*\r?\n",
        "\r\n",
        text,
    )

    # Re-find eventFilter (offset may have shifted)
    ef_match = ef_pattern.search(text)
    if not ef_match:
        raise RuntimeError("Cannot find eventFilter function after cleanup")

    # Inject the new hitButton diagnostic at the top of eventFilter.
    diag_block = (
        ef_match.group(1) +
        f"    // --- {MARKER}: capture position, rect, hitButton, isDown ---\r\n"
        "    if (watched == addButton_)\r\n"
        "    {\r\n"
        "        const QEvent::Type t = event->type();\r\n"
        "        if (t == QEvent::MouseButtonPress ||\r\n"
        "            t == QEvent::MouseButtonRelease)\r\n"
        "        {\r\n"
        "            auto *me = static_cast<QMouseEvent *>(event);\r\n"
        "            const QPoint pos = me->position().toPoint();\r\n"
        "            const QRect r = addButton_->rect();\r\n"
        "            const bool contains = r.contains(pos);\r\n"
        "            qDebug() << \"[ChainStudio] btn event\" << t\r\n"
        "                     << \"e->pos=\" << pos\r\n"
        "                     << \"rect=\" << r\r\n"
        "                     << \"contains=\" << contains\r\n"
        "                     << \"isDown=\" << addButton_->isDown()\r\n"
        "                     << \"isEnabled=\" << addButton_->isEnabled()\r\n"
        "                     << \"isVisible=\" << addButton_->isVisible()\r\n"
        "                     << \"button=\" << me->button();\r\n"
        "        }\r\n"
        "    }\r\n\r\n"
    )
    text = text.replace(ef_match.group(1), diag_block, 1)

    path.write_text(text, encoding="utf-8")
    print(f"  Patched: {path.name}")
    print()
    print(f"Done — {MARKER} applied.")
    print()
    print("Run: .\\scripts\\dev\\run_ui.ps1")
    print("Then click the + add stage button ONCE.")
    print()
    print("Look for output like:")
    print("  [ChainStudio] btn event QEvent::MouseButtonPress  e->pos= QPoint(X,Y)")
    print("               rect= QRect(0,0 WxH)  contains= true   isDown= false")
    print("               isEnabled= true   isVisible= true   button= LeftButton")
    print("  [ChainStudio] btn event QEvent::MouseButtonRelease  e->pos= QPoint(X,Y)")
    print("               rect= QRect(0,0 WxH)  contains= ???    isDown= ???")
    print()
    print("INTERPRETATION:")
    print("  PRESS contains=true, RELEASE isDown=true, RELEASE contains=true:")
    print("    Per Qt source, click() should fire. This would mean a different")
    print("    code path is suppressing it (event filter, style, etc).")
    print()
    print("  PRESS contains=false: hitButton returns false on press,")
    print("    button never goes down, no click. Geometry/transformation issue.")
    print()
    print("  PRESS contains=true, RELEASE isDown=false: something resets the")
    print("    down state between press and release. Mouse move event firing")
    print("    a hitButton-mismatch reset, or focus change, or...")
    print()
    print("  PRESS contains=true, RELEASE isDown=true, RELEASE contains=false:")
    print("    The release event's local pos is outside the button rect, even")
    print("    though it was dispatched to the button. Stylesheet/padding issue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
