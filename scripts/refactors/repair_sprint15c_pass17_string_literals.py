from pathlib import Path
import re

path = Path("qt_ui/T2VHistoryPage.cpp")
text = path.read_text(encoding="utf-8")

# Fix broken multiline QStringLiteral in the "could not write draft" warning.
text = re.sub(
    r'QStringLiteral\("Could not write requeue draft:\s*\n%1"\)\.arg\(draftPath\)',
    r'QStringLiteral("Could not write requeue draft:\\n%1").arg(draftPath)',
    text,
    flags=re.MULTILINE,
)

# Fix broken multiline QStringLiteral in the success message.
text = re.sub(
    r'QStringLiteral\("Created a safe LTX requeue draft and copied its path to the clipboard\.\s*\n\s*\n%1"\)\.arg\(draftPath\)',
    r'QStringLiteral("Created a safe LTX requeue draft and copied its path to the clipboard.\\n\\n%1").arg(draftPath)',
    text,
    flags=re.MULTILINE,
)

# Extra defensive cleanup if PowerShell/Python inserted literal line breaks between quote boundaries.
text = text.replace(
    'QStringLiteral("Could not write requeue draft:\n%1").arg(draftPath)',
    'QStringLiteral("Could not write requeue draft:\\\\n%1").arg(draftPath)',
)

text = text.replace(
    'QStringLiteral("Created a safe LTX requeue draft and copied its path to the clipboard.\n\n%1").arg(draftPath)',
    'QStringLiteral("Created a safe LTX requeue draft and copied its path to the clipboard.\\\\n\\\\n%1").arg(draftPath)',
)

path.write_text(text, encoding="utf-8")

print("Fixed Pass 17 multiline QStringLiteral escaping.")
