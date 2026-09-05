"""Pull one file from Hugging Face with urllib, streaming, resumable.

Why urllib and not huggingface_hub / httpx / curl: on this box only the plain urllib GET of the
`resolve/main` URL completes for multi-gigabyte files (banked 2026-08). Writes to `<name>.part` and
renames on completion, honouring an existing partial with a Range request, so a dropped connection
costs nothing but the retry. Progress every 256 MB to stdout so a detached run has a log.

    python scripts/dev/pull_hf_file.py Comfy-Org/Qwen3-VL text_encoders/qwen3vl_4b_bf16.safetensors F:/AI_ASSETS/models/text_encoders
"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

repo, path_in_repo, dest_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
url = f"https://huggingface.co/{repo}/resolve/main/{path_in_repo}"
dest = dest_dir / Path(path_in_repo).name
part = dest.with_suffix(dest.suffix + ".part")
dest_dir.mkdir(parents=True, exist_ok=True)

if dest.exists():
    print(f"already present: {dest} ({dest.stat().st_size / 2**30:.2f} GB)")
    raise SystemExit(0)

have = part.stat().st_size if part.exists() else 0
headers = {"User-Agent": "spellvision-pull/1.0"}
if have:
    headers["Range"] = f"bytes={have}-"
    print(f"resuming at {have / 2**30:.2f} GB")

request = urllib.request.Request(url, headers=headers)
started = time.time()
with urllib.request.urlopen(request, timeout=120) as response:
    total = response.headers.get("Content-Length")
    total = have + int(total) if total else None
    status = response.status
    if have and status != 206:
        print(f"server ignored Range (status {status}); restarting from zero")
        have = 0
    mode = "ab" if have else "wb"
    print(f"{url}\n-> {part}  total {total / 2**30:.2f} GB" if total else f"{url}\n-> {part}")
    done = have
    next_report = done + 256 * 2**20
    with open(part, mode) as f:
        while True:
            chunk = response.read(8 * 2**20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if done >= next_report:
                rate = (done - have) / max(time.time() - started, 1e-6) / 2**20
                pct = f" {done * 100 / total:5.1f}%" if total else ""
                print(f"  {done / 2**30:6.2f} GB{pct}  {rate:6.1f} MB/s  {time.strftime('%H:%M:%S')}", flush=True)
                next_report = done + 256 * 2**20

if total and done != total:
    print(f"INCOMPLETE: {done} of {total} bytes; rerun to resume")
    raise SystemExit(1)
os.replace(part, dest)
print(f"DONE {dest} ({done / 2**30:.2f} GB) in {(time.time() - started) / 60:.1f} min")
