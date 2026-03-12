# SPELLVISION_INSTALLATION_GUIDE.md

## SpellVision Installation Guide

This guide explains how to install and configure SpellVision on a
Windows workstation.

Recommended hardware:

-   NVIDIA RTX 5090 (or similar high-end GPU)
-   32--128 GB RAM
-   NVMe SSD storage
-   Windows 11

------------------------------------------------------------------------

# 1. Required Software

Install the following:

-   Git
-   Python 3.12+
-   Rust
-   CMake
-   Qt 6 (MSVC build)
-   Visual Studio Build Tools (MSVC + Windows SDK)
-   NVIDIA Drivers (latest)

Optional but recommended:

-   Ollama
-   Blender

------------------------------------------------------------------------

# 2. Clone the Repository

``` bash
git clone https://github.com/yourrepo/SpellVision.git
cd SpellVision
```

------------------------------------------------------------------------

# 3. Create Python Virtual Environment

``` powershell
python -m venv .venv
```

Activate:

``` powershell
.\.venv\Scripts\Activate.ps1
```

------------------------------------------------------------------------

# 4. Install Python Dependencies

Install PyTorch (CUDA build):

``` powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Install generation libraries:

``` powershell
pip install diffusers transformers accelerate safetensors pillow
pip install sentencepiece protobuf
```

Optional performance tools:

``` powershell
pip install xformers
```

------------------------------------------------------------------------

# 5. Install Ollama (Optional but Recommended)

Download:

https://ollama.com

Pull recommended model:

``` bash
ollama pull mistral-small
```

This will allow SpellVision to:

-   optimize prompts
-   generate negative prompts
-   recommend LoRAs

------------------------------------------------------------------------

# 6. Configure Qt

Ensure Qt is installed (example path):

    C:/Qt/6.10.2/msvc2022_64/

Configure CMake:

``` powershell
cmake -S . -B build -DQt6_DIR="C:/Qt/6.10.2/msvc2022_64/lib/cmake/Qt6"
```

------------------------------------------------------------------------

# 7. Build SpellVision

``` powershell
cmake --build build --config Debug
```

------------------------------------------------------------------------

# 8. Deploy Qt Runtime

``` powershell
C:\Qt\6.10.2\msvc2022_64\bin\windeployqt.exe build\Debug\SpellVision.exe
```

------------------------------------------------------------------------

# 9. Run SpellVision

``` powershell
build\Debug\SpellVision.exe
```

------------------------------------------------------------------------

# 10. Model Directory

Recommended structure:

    models/
      checkpoints/
      loras/
      video/
      3d/

Model weights should **not be committed to Git**.

------------------------------------------------------------------------

# 11. GPU Verification

Check CUDA availability:

``` python
import torch
print(torch.cuda.is_available())
print(torch.cuda.get_device_name())
```

Expected output should show your RTX 5090.

------------------------------------------------------------------------

# 12. Troubleshooting

### Qt build errors

Ensure MSVC and Windows SDK are installed.

### Worker connection errors

Ensure `worker_service.py` is running.

### LoRA not affecting output

Verify:

-   LoRA compatible with model
-   scale \> 0.6
-   correct path

------------------------------------------------------------------------

SpellVision should now be ready to generate images.
