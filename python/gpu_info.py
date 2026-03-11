import json
import sys

try:
    import torch

    info = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count(),
        "devices": [],
    }

    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            total_gb = round(props.total_memory / (1024 ** 3), 2)
            reserved_gb = round(torch.cuda.memory_reserved(i) / (1024 ** 3), 2)
            allocated_gb = round(torch.cuda.memory_allocated(i) / (1024 ** 3), 2)
            free_gb = round(max(total_gb - reserved_gb, 0), 2)

            info["devices"].append({
                "index": i,
                "name": props.name,
                "total_vram_gb": total_gb,
                "reserved_vram_gb": reserved_gb,
                "allocated_vram_gb": allocated_gb,
                "approx_free_vram_gb": free_gb,
                "major": props.major,
                "minor": props.minor,
            })

    print(json.dumps(info))
except Exception as e:
    print(json.dumps({
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
        "error": str(e),
    }))
    sys.exit(0)