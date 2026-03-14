$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\..\..")

Write-Host "==> Activating venv" -ForegroundColor Cyan
& .\.venv\Scripts\Activate.ps1

Write-Host "==> Python version" -ForegroundColor Cyan
python -V

Write-Host "==> Python syntax check" -ForegroundColor Cyan
python -m py_compile python\worker_service.py python\worker_client.py

Write-Host "==> Torch / CUDA check" -ForegroundColor Cyan
python -c "import torch; print('torch=', torch.__version__, 'cuda=', torch.version.cuda, 'gpu=', torch.cuda.is_available())"

Write-Host "==> Diffusers / Transformers / PEFT check" -ForegroundColor Cyan
python -c "import diffusers, transformers, peft, PIL; print('diffusers=', diffusers.__version__, 'transformers=', transformers.__version__, 'peft=', peft.__version__)"

Write-Host "==> Queue status check" -ForegroundColor Cyan
'{"command":"queue_status"}' | python .\python\worker_client.py

Write-Host "==> Backend checks completed" -ForegroundColor Green