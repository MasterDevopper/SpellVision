from pathlib import Path
import re

path = Path("qt_ui/T2VHistoryPage.cpp")
text = path.read_text(encoding="utf-8")

# Remove the free helper that illegally references private T2VHistoryPage::VideoHistoryItem.
text = re.sub(
    r'\nQString\s+expectedLtxRequeueDraftPathForItem\s*\(\s*const\s+T2VHistoryPage::VideoHistoryItem\s*&\s*item\s*\)\s*\{.*?\n\}\s*\n',
    "\n",
    text,
    count=1,
    flags=re.DOTALL,
)

# Compute the draft path inside the class member function instead.
old = '    const QString draftPath = expectedLtxRequeueDraftPathForItem(*item);\n'
new = '''    const QString promptId = requeuePromptIdFromRuntimeSummary(item->runtimeSummary);
    const QString slug = safeRequeueSlug(promptId.isEmpty() ? item->promptPreview.left(80) : promptId);
    const QString draftPath = QDir(ltxRequeueDraftRoot()).filePath(QStringLiteral("%1.requeue.json").arg(slug));
'''

if old not in text:
    raise SystemExit("Could not find expectedLtxRequeueDraftPathForItem call in validateSelectedLtxRequeueDraft().")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

print("Repaired Pass 19 private VideoHistoryItem helper issue.")
