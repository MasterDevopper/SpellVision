"""Standalone probe that prints CUDA device facts as JSON on stdout.

A SCRIPT, not a module: importing it runs torch and prints. Intended to be executed in a
subprocess so a torch/CUDA failure cannot take the caller down with it -- which is why the whole
body sits in a try/except that still exits 0, reporting ``cuda_available: false`` plus the error
rather than a traceback.

**Nothing in the tree calls it.** The live VRAM readout is on the C++ side, in
``qt_ui/shell/GpuMemoryProbe``, which loads NVML directly (an ``nvidia-smi`` subprocess measured
46 ms against roughly 3 us for NVML, and this is polled). This file is a manual diagnostic only --
do not import it to obtain GPU facts.

Note the numbers here are torch's view: ``free`` is derived as total minus torch's RESERVED block,
so it describes what this process could still allocate, not what the device has free overall.
"""
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