from pathlib import Path
import re

path = Path("python/ltx_requeue_draft_submission.py")
text = path.read_text(encoding="utf-8")

text = re.sub(
    r'"ok":\s*bool\(gated\.get\("ok",\s*True\)\),',
    '"ok": bool(gated.get("ok", True)) if should_submit else True,',
    text,
    count=1,
)

path.write_text(text, encoding="utf-8")

print("Forced Pass 18 dry-run wrapper ok=True when draft is valid.")
