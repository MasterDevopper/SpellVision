$patch = @'
"""
VRAM Pass (follow-up): promote the fp32->fp16 cast confirmation to WARNING.

memory_optimization.py uses ``log = logging.getLogger(__name__)`` with no
level, no handler, and no basicConfig anywhere in the worker. The logger
therefore inherits the root logger's default level of WARNING. That is
why the "Silent dtype fallback detected" line (log.warning) appears in
worker_service.stderr.log but the "fp32->fp16 cast applied" line
(log.info) never does -- INFO is below the effective threshold.

The cast confirmation belongs at WARNING anyway: a fp32-on-disk
checkpoint forcing a runtime cast is the same class of "you should know
this happened" information as the silent-fallback warning it answers.
They are a matched pair -- one says "this checkpoint shipped fp32", the
other says "...so here is what was done about it". Both should be
visible in the same log at the same level.

This is a one-token change: log.info -> log.warning on exactly that
call. No behavior changes; the cast already runs. This only makes its
result auditable.

Must run AFTER apply_vram_fp16_cast_memory_optimization.ps1, since it
edits text that patch introduced.
"""
from pathlib import Path
path = Path("python/memory_optimization.py")
text = path.read_text(encoding="utf-8")

needle = '''            fp32_cast_applied = True
            log.info(
                "fp32->fp16 cast applied on CPU before device move "
                "(checkpoint had no fp16 weights on disk): %s",
                model_name_or_path,
            )'''

replacement = '''            fp32_cast_applied = True
            # WARNING level (not INFO): this logger inherits the root
            # default of WARNING, and this line is the matched answer to
            # the "Silent dtype fallback detected" warning -- both should
            # be visible in the worker log.
            log.warning(
                "fp32->fp16 cast applied on CPU before device move "
                "(checkpoint had no fp16 weights on disk): %s",
                model_name_or_path,
            )'''

if needle not in text:
    raise SystemExit(
        "Could not find the fp32 cast log.info block. "
        "Ensure apply_vram_fp16_cast_memory_optimization.ps1 was applied first."
    )
text = text.replace(needle, replacement, 1)
path.write_text(text, encoding="utf-8")
print("Applied VRAM Pass follow-up: fp32 cast confirmation promoted to WARNING level.")
'@
Set-Content .\scripts\refactors\apply_vram_fp16_cast_log_level.py $patch -Encoding UTF8
.\.venv\Scripts\python.exe .\scripts\refactors\apply_vram_fp16_cast_log_level.py
