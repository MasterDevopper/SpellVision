#include "GpuMemoryProbe.h"

namespace
{
constexpr unsigned int kNvmlSuccess = 0;

// nvmlMemory_t (v1).
struct NvmlMemory
{
    unsigned long long total = 0;
    unsigned long long free = 0;
    unsigned long long used = 0;
};

// nvmlMemory_v2_t. The v2 entry point is the one that matches what nvidia-smi prints: v1 folds
// the driver-reserved block into `used`, which on this box reads 3324 MiB against nvidia-smi's
// 2905 -- a silent ~420 MiB inflation of a user-facing number. v2 splits `reserved` out, so
// `used` means the same thing the bottom bar has always shown. v1 stays as the fallback for
// drivers too old to know the v2 symbol, and is documented as reading high.
struct NvmlMemoryV2
{
    unsigned int version = 0;
    unsigned long long total = 0;
    unsigned long long reserved = 0;
    unsigned long long free = 0;
    unsigned long long used = 0;
};

// The nvmlMemory_v2 macro from nvml.h: struct size in the low bits, version in bits 24+.
constexpr unsigned int kNvmlMemoryV2Version =
    static_cast<unsigned int>(sizeof(NvmlMemoryV2)) | (2u << 24);

constexpr double kBytesPerMb = 1024.0 * 1024.0;
} // namespace

GpuMemoryProbe &GpuMemoryProbe::instance()
{
    static GpuMemoryProbe probe;
    return probe;
}

GpuMemoryProbe::~GpuMemoryProbe()
{
    if (loaded_ && shutdown_)
        shutdown_();
}

bool GpuMemoryProbe::ensureLoaded()
{
    if (loadAttempted_)
        return loaded_;

    loadAttempted_ = true;

    library_.setFileName(QStringLiteral("nvml"));
    if (!library_.load())
        return false;

    init_ = reinterpret_cast<InitFn>(library_.resolve("nvmlInit_v2"));
    shutdown_ = reinterpret_cast<ShutdownFn>(library_.resolve("nvmlShutdown"));
    handleByIndex_ = reinterpret_cast<HandleFn>(library_.resolve("nvmlDeviceGetHandleByIndex_v2"));
    memoryInfo_ = reinterpret_cast<MemoryFn>(library_.resolve("nvmlDeviceGetMemoryInfo"));
    memoryInfoV2_ = reinterpret_cast<MemoryFn>(library_.resolve("nvmlDeviceGetMemoryInfo_v2"));

    if (!init_ || !handleByIndex_ || !memoryInfo_)
    {
        library_.unload();
        return false;
    }

    if (init_() != kNvmlSuccess)
    {
        library_.unload();
        return false;
    }

    if (handleByIndex_(0, &device_) != kNvmlSuccess || device_ == nullptr)
    {
        if (shutdown_)
            shutdown_();
        library_.unload();
        return false;
    }

    loaded_ = true;
    return true;
}

bool GpuMemoryProbe::isAvailable()
{
    return ensureLoaded();
}

GpuMemoryProbe::Reading GpuMemoryProbe::read()
{
    Reading reading;
    if (!ensureLoaded())
        return reading;

    if (memoryInfoV2_)
    {
        NvmlMemoryV2 memory;
        memory.version = kNvmlMemoryV2Version;
        if (memoryInfoV2_(device_, &memory) == kNvmlSuccess && memory.total != 0)
        {
            reading.valid = true;
            reading.usedMb = static_cast<double>(memory.used) / kBytesPerMb;
            reading.totalMb = static_cast<double>(memory.total) / kBytesPerMb;
            return reading;
        }
    }

    NvmlMemory memory;
    if (memoryInfo_(device_, &memory) != kNvmlSuccess)
        return reading;

    if (memory.total == 0)
        return reading;

    reading.valid = true;
    reading.usedMb = static_cast<double>(memory.used) / kBytesPerMb;
    reading.totalMb = static_cast<double>(memory.total) / kBytesPerMb;
    return reading;
}
