from pathlib import Path
import re

service_path = Path("python/worker_service.py")
service = service_path.read_text(encoding="utf-8")

bad_block = '''            if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:
                runtime_status = handle_comfy_runtime_status_command({})
                emitter.emit(ltx_requeue_draft_gated_submission_snapshot(req, runtime_status=runtime_status))
                return

'''

good_block = '''        if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:
            runtime_status = handle_comfy_runtime_status_command({})
            emitter.emit(ltx_requeue_draft_gated_submission_snapshot(req, runtime_status=runtime_status))
            return

'''

# Remove unreachable nested block if present.
service = service.replace(bad_block, "")

# Insert reachable block before the existing gated submission route.
if 'if command in {"ltx_requeue_draft_gated_submission", "ltx_execute_requeue_draft", "video_family_ltx_requeue_gated_submission"}:' not in service:
    marker = '''        if command in {"ltx_prompt_api_gated_submission", "ltx_prompt_api_submit", "ltx_submit_prompt_api", "ltx_prompt_api_submit_and_capture", "ltx_prompt_api_submit_wait", "video_family_prompt_api_gated_submission"}:
'''
    if marker not in service:
        raise SystemExit("Could not find correctly indented LTX gated submission marker.")

    service = service.replace(marker, good_block + marker, 1)

service_path.write_text(service, encoding="utf-8")

print("Moved Pass 18 LTX requeue route into reachable dispatcher scope.")
