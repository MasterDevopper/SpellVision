param(
    [string]$ComfyRoot = $env:SPELLVISION_COMFY,
    [string]$ModelsRoot = $env:SPELLVISION_MODELS
)

$ErrorActionPreference = "Stop"

if (-not $ComfyRoot -or $ComfyRoot.Trim().Length -eq 0) {
    if ($env:SPELLVISION_ASSETS) {
        $ComfyRoot = Join-Path $env:SPELLVISION_ASSETS "comfy_runtime\ComfyUI"
    } else {
        $ComfyRoot = "D:\AI_ASSETS\comfy_runtime\ComfyUI"
    }
}
if (-not $ModelsRoot -or $ModelsRoot.Trim().Length -eq 0) {
    if ($env:SPELLVISION_ASSETS) {
        $ModelsRoot = Join-Path $env:SPELLVISION_ASSETS "models"
    } else {
        $ModelsRoot = "D:\AI_ASSETS\models"
    }
}

$ComfyRoot = [System.IO.Path]::GetFullPath($ComfyRoot)
$ModelsRoot = [System.IO.Path]::GetFullPath($ModelsRoot)
$extraPath = Join-Path $ComfyRoot "extra_model_paths.yaml"

$folders = @(
    "checkpoints", "configs", "diffusion_models", "vae", "text_encoders",
    "clip_vision", "loras", "controlnet", "embeddings", "upscale_models"
)
foreach ($folder in $folders) {
    New-Item -ItemType Directory -Path (Join-Path $ModelsRoot $folder) -Force | Out-Null
}

$modelsYamlPath = $ModelsRoot.Replace("\", "/")
$begin = "# >>> SpellVision managed model paths >>>"
$end = "# <<< SpellVision managed model paths <<<"
$block = @"
$begin
spellvision:
    base_path: $modelsYamlPath
    checkpoints: checkpoints
    configs: configs
    vae: vae
    clip: text_encoders
    text_encoders: text_encoders
    clip_vision: clip_vision
    loras: loras
    controlnet: controlnet
    embeddings: embeddings
    upscale_models: upscale_models
    unet: diffusion_models
    diffusion_models: diffusion_models
$end
"@

$existing = ""
if (Test-Path $extraPath) {
    $existing = Get-Content $extraPath -Raw
}

if ($existing.Contains($begin) -and $existing.Contains($end)) {
    $pattern = [regex]::Escape($begin) + "(?s).*?" + [regex]::Escape($end)
    $updated = [regex]::Replace($existing, $pattern, $block.TrimEnd())
} elseif ($existing.Trim().Length -gt 0) {
    $updated = $existing.TrimEnd() + "`r`n`r`n" + $block
} else {
    $updated = $block
}

New-Item -ItemType Directory -Path $ComfyRoot -Force | Out-Null
Set-Content -Path $extraPath -Value $updated -Encoding UTF8

Write-Host "Updated Comfy extra model paths:" $extraPath
Write-Host "SpellVision models root:" $ModelsRoot
Write-Host "Restart ComfyUI so /object_info reloads the model lists."
