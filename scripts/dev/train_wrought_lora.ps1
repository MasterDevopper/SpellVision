<#
.SYNOPSIS
  Train the Wrought style LoRA on Krea 2 / Utopic with musubi-tuner, from the owner's picks.

.DESCRIPTION
  Three stages, each skippable: pre-cache latents (VAE), pre-cache text-encoder outputs (Qwen3-VL),
  train. Recipe is musubi-tuner docs/krea2.md (rank 32 / alpha 32, lr 1e-4, adamw8bit, timestep
  sampling "shift" with discrete flow shift 2.5 at 1024, bf16, gradient checkpointing), which
  contains Doc 43's numbers. Trains on the RAW-class checkpoint (Utopic v20BF16 by default -- the
  same lineage the dataset was rendered on; pass -Dit for krea2_raw), never on Turbo; samples during
  training are rendered on Turbo with the LoRA applied, which is where the look is judged.

  NOT to be run while ComfyUI is rendering on this box: the text encoder and DiT go into host RAM
  first and DynamicVRAM pages there -- free RAM under ~8 GB collapses ComfyUI throughput twenty-fold.

.EXAMPLE
  .\scripts\dev\train_wrought_lora.ps1 -Name wrought_v1
  .\scripts\dev\train_wrought_lora.ps1 -Name wrought_v1 -SkipCache -Epochs 20
#>
param(
    [string]$Name = "wrought_v1",
    [string]$Musubi = "C:\sv_musubi\musubi-tuner",
    [string]$Models = "F:\AI_ASSETS\models",
    [string]$Dit = "diffusion_models\loxsUtopicWorldKrea2_v20BF16.safetensors",
    [string]$Turbo = "diffusion_models\krea2_turbo_fp8_scaled.safetensors",
    [string]$TextEncoder = "text_encoders\qwen3vl_4b_fp8_scaled.safetensors",
    [string]$Vae = "vae\qwen_image_vae.safetensors",
    [string]$Dataset = "$PSScriptRoot\..\..\runtime\style\datasets\wrought_night_v1\dataset.toml",
    [string]$OutDir = "$PSScriptRoot\..\..\runtime\style\loras",
    [int]$Rank = 32,
    [int]$Alpha = 32,
    [double]$LR = 1e-4,
    [int]$Epochs = 16,
    [int]$SaveEvery = 1,
    [int]$SampleEvery = 2,
    [switch]$Fp8Dit,
    [switch]$SkipCache,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"   # the trainer's help text has non-cp1252 characters; same requirement as the ComfyUI launcher
$py = Join-Path $Musubi ".venv\Scripts\python.exe"
$src = Join-Path $Musubi "src\musubi_tuner"
$dit = Join-Path $Models $Dit
$turbo = Join-Path $Models $Turbo
$te = Join-Path $Models $TextEncoder
$vae = Join-Path $Models $Vae
$Dataset = (Resolve-Path $Dataset).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

foreach ($f in @($py, $dit, $te, $vae, $Dataset)) {
    if (-not (Test-Path $f)) { throw "missing: $f" }
}

# Sample prompts: three fixed-seed checks per checkpoint, per the community rule -- in-distribution
# (an orc in the house look), generalisation (a subject the set never had), and control (no trigger,
# must stay close to base). Turbo: 8 steps, CFG off, mu 1.15.
$samples = Join-Path $OutDir "$Name.samples.txt"
@"
wrought style, a single orc woman, warrior athletic, a young adult in their mid-twenties, long hair in a single thick braid, calm and level expression, wearing a studded leather jerkin over a padded shirt, well kept but used, waist-up portrait, key light from the upper left --w 768 --h 1024 --s 8 --l 1 --d 1002
wrought style, a weathered stone watchtower on a cliff at dusk, iron-banded door, moss in the mortar, single hard key light --w 1024 --h 768 --s 8 --l 1 --d 7
a single orc woman, warrior athletic, long hair in a single thick braid, wearing a studded leather jerkin, waist-up portrait --w 768 --h 1024 --s 8 --l 1 --d 1002
"@ | Set-Content -Path $samples -Encoding UTF8

$cache1 = @($py, "$src\krea2_cache_latents.py", "--dataset_config", $Dataset, "--vae", $vae)
$cache2 = @($py, "$src\krea2_cache_text_encoder_outputs.py", "--dataset_config", $Dataset,
            "--text_encoder", $te, "--batch_size", "1")
$train = @($py, "-m", "accelerate.commands.launch", "--num_cpu_threads_per_process", "1",
           "--mixed_precision", "bf16", "$src\krea2_train_network.py",
           "--dit", $dit, "--vae", $vae, "--text_encoder", $te, "--dataset_config", $Dataset,
           "--sdpa", "--mixed_precision", "bf16",
           "--timestep_sampling", "shift", "--weighting_scheme", "none", "--discrete_flow_shift", "2.5",
           "--optimizer_type", "adamw8bit", "--learning_rate", "$LR",
           "--gradient_checkpointing", "--max_data_loader_n_workers", "2", "--persistent_data_loader_workers",
           "--network_module", "networks.lora_krea2", "--network_dim", "$Rank", "--network_alpha", "$Alpha",
           "--max_train_epochs", "$Epochs", "--save_every_n_epochs", "$SaveEvery", "--seed", "42",
           "--sample_prompts", $samples, "--sample_every_n_epochs", "$SampleEvery", "--turbo_dit", $turbo,
           "--output_dir", $OutDir, "--output_name", $Name)
if ($Fp8Dit) { $train += @("--fp8_base", "--fp8_scaled") }

function Run($argv, $label) {
    Write-Host "==> $label" -ForegroundColor Cyan
    Write-Host ("    " + ($argv -join " "))
    if ($DryRun) { return }
    & $argv[0] $argv[1..($argv.Length - 1)]
    if ($LASTEXITCODE -ne 0) { throw "$label failed ($LASTEXITCODE)" }
}

Push-Location $Musubi
try {
    if (-not $SkipCache) {
        Run $cache1 "cache latents (VAE)"
        Run $cache2 "cache text-encoder outputs (Qwen3-VL)"
    }
    Run $train "train $Name"
} finally {
    Pop-Location
}
Write-Host "==> LoRA checkpoints in $OutDir ; load in ComfyUI via LoraLoaderModelOnly on the Turbo or Utopic UNET" -ForegroundColor Green
