from pathlib import Path
import re

path = Path("python/ltx_prompt_api_submission.py")
text = path.read_text(encoding="utf-8")

if "LTX_VIDEO_OUTPUT_EXTENSIONS" not in text:
    anchor = 'from ltx_queue_history_registry import register_ltx_queue_history_result\n\n\n'
    insert = '''from ltx_queue_history_registry import register_ltx_queue_history_result


LTX_VIDEO_OUTPUT_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}


def _ltx_output_media_type(filename: str, bucket: str, animated: bool | None) -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix in LTX_VIDEO_OUTPUT_EXTENSIONS:
        return "video"
    if bucket in {"videos", "gifs"}:
        return "video"
    if bucket == "audio":
        return "audio"
    if animated:
        return "video"
    return "image"


'''
    if anchor not in text:
        raise SystemExit("Could not find import anchor for media type helper.")
    text = text.replace(anchor, insert, 1)

old = '''                        "animated": animated,
                    }
                )
'''

new = '''                        "animated": animated,
                        "media_type": _ltx_output_media_type(filename, bucket_name, animated),
                    }
                )
'''

if old not in text:
    raise SystemExit("Could not find output extraction append block.")

text = text.replace(old, new, 1)

old2 = '''                "kind": "video",
'''
new2 = '''                "kind": str(output.get("media_type") or "video"),
'''

if old2 not in text:
    raise SystemExit("Could not find output record kind line.")

text = text.replace(old2, new2, 1)

path.write_text(text, encoding="utf-8")
print("Applied Sprint 15C Pass 29K media-type hardening.")
