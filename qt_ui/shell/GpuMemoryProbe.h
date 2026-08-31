#pragma once

// System-wide GPU memory without spawning a process.
//
// The bottom-bar VRAM readout has to be system-wide -- ComfyUI is a separate process, so the
// worker's torch.cuda numbers only ever describe the worker itself. That left `nvidia-smi`,
// which measured at ~46ms per invocation and was being spawned every 2000ms for the whole life
// of the app. NVML is the same data from the same driver: ~3us per query and no process at all.
//
// nvml.dll ships with every NVIDIA driver (System32 on Windows). It is loaded lazily and
// resolved by name, so there is no link-time dependency and no requirement that it exist --
// callers fall back to nvidia-smi when isAvailable() is false.
//
// Not thread-safe; call from one thread (the UI thread, off the telemetry timer).

#include <QLibrary>

class GpuMemoryProbe
{
public:
    struct Reading
    {
        bool valid = false;
        double usedMb = 0.0;
        double totalMb = 0.0;
    };

    static GpuMemoryProbe &instance();

    // True once NVML has loaded and device 0 has been resolved. Cheap after the first call.
    bool isAvailable();

    // Queries device 0 -- matching the single line the nvidia-smi path parsed. Returns an
    // invalid Reading if NVML is unavailable or the query fails (a driver reset invalidates the
    // cached handle), which is the caller's cue to fall back.
    Reading read();

private:
    GpuMemoryProbe() = default;
    ~GpuMemoryProbe();
    GpuMemoryProbe(const GpuMemoryProbe &) = delete;
    GpuMemoryProbe &operator=(const GpuMemoryProbe &) = delete;

    bool ensureLoaded();

    QLibrary library_;
    bool loadAttempted_ = false;
    bool loaded_ = false;
    void *device_ = nullptr;

    using InitFn = unsigned int (*)();
    using ShutdownFn = unsigned int (*)();
    using HandleFn = unsigned int (*)(unsigned int, void **);
    using MemoryFn = unsigned int (*)(void *, void *);

    InitFn init_ = nullptr;
    ShutdownFn shutdown_ = nullptr;
    HandleFn handleByIndex_ = nullptr;
    MemoryFn memoryInfo_ = nullptr;
    // Preferred: v1 reports the driver-reserved block as used, v2 does not (see the .cpp).
    MemoryFn memoryInfoV2_ = nullptr;
};
