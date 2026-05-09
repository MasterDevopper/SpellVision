from pathlib import Path

path = Path("python/ltx_prompt_api_submission.py")
text = path.read_text(encoding="utf-8")

old = '''    if not comfy_running:
        blocked_reasons.append("comfy_not_running")
'''

new = '''    # Sprint 15C Pass 29J:
    # Treat an externally launched ComfyUI as running when the endpoint is healthy.
    # The runtime manager may report running=False when SpellVision did not launch
    # the process itself, but Prompt API submission only needs a reachable healthy
    # endpoint.
    if not (comfy_running or comfy_healthy or endpoint_alive):
        blocked_reasons.append("comfy_not_running")
    else:
        comfy_running = True
'''

if old not in text:
    raise SystemExit("Could not find comfy_running block in python/ltx_prompt_api_submission.py")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("Applied Sprint 15C Pass 29J: external healthy Comfy counts as running for LTX Prompt API submission.")
