from pathlib import Path

path = Path("python/worker_service.py")
text = path.read_text(encoding="utf-8")

old = '''        # Product default: Full is the final-quality primary candidate.
        return "full"
'''

new = '''        # Sprint 15C Pass 29P v5:
        # Match the visible UI default. The LTX Launch Options panel defaults
        # Preferred output to "distilled", so missing request fields should not
        # silently promote Full.
        return "distilled"
'''

if old not in text:
    raise SystemExit("Could not find preferred-output default return block in worker_service.py")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29P v5: backend preferred-output fallback now matches UI default distilled.")
