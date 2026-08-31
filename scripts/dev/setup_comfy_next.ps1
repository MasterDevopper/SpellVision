<#
.SYNOPSIS
  Doc 25 S1 -- stand up a parallel ComfyUI instance for a gated core bump. Non-destructive.

.DESCRIPTION
  Builds a complete second ComfyUI at $Tag with its OWN venv, sharing only the read-only model
  store via extra_model_paths.yaml. The live install on :8188 is never touched, so a failed bump
  costs nothing and rollback is "stop using the new port".

  Custom node packs are pinned to the SHAs the LIVE install is running, deliberately deviating from
  Doc 25 S1's "clone each at its latest commit". Bumping core and six packs together means a
  regression has seven suspects; pinning the packs makes the core the only variable. Update packs
  as a separate pass once the core is proven.

.PARAMETER Tag
  ComfyUI release tag to check out. All of v0.33.1 / v0.33.4 / v0.34.0 pre-screened clean against
  our node contract -- see docs/pipeline/comfy_baselines/README.md.

.EXAMPLE
  .\scripts\dev\setup_comfy_next.ps1 -Tag v0.34.0
  .\scripts\dev\setup_comfy_next.ps1 -Tag v0.34.0 -SkipVenv   # tree + configs only
#>
param(
    [string]$Tag        = "v0.34.0",
    [string]$Root       = "C:\sv_comfynext_v034",
    [string]$LiveRoot   = "C:\sv_comfynext\ComfyUI",
    [int]   $Port       = 8189,
    [switch]$SkipVenv,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "==> $m" }

$comfyDir = Join-Path $Root "ComfyUI"
$venvDir  = Join-Path $Root ".venv"
$venvPy   = Join-Path $venvDir "Scripts\python.exe"

# --- guard: never let this script point at the live install -------------------------------------
if ((Resolve-Path -LiteralPath $LiveRoot -ErrorAction SilentlyContinue) -and
    $comfyDir -eq (Resolve-Path -LiteralPath $LiveRoot).Path) {
    throw "refusing to run: target $comfyDir IS the live install"
}

# --- core ----------------------------------------------------------------------------------------
if (Test-Path (Join-Path $comfyDir ".git")) {
    Say "core already present; fetching $Tag"
    git -C $comfyDir fetch --depth 1 origin "refs/tags/$($Tag):refs/tags/$Tag" 2>&1 | Out-Null
    git -C $comfyDir checkout --quiet $Tag
} else {
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Say "cloning ComfyUI $Tag -> $comfyDir"
    git clone --quiet --depth 1 --branch $Tag https://github.com/comfyanonymous/ComfyUI.git $comfyDir
}
Say "core at $(git -C $comfyDir rev-parse --short HEAD) ($Tag)"

# --- shared model store ---------------------------------------------------------------------------
# Copied, not symlinked: the new instance must be able to diverge (e.g. a target-only model path)
# without editing the live install's config.
$liveYaml = Join-Path $LiveRoot "extra_model_paths.yaml"
if (Test-Path $liveYaml) {
    Copy-Item $liveYaml (Join-Path $comfyDir "extra_model_paths.yaml") -Force
    Say "copied extra_model_paths.yaml (models stay shared + read-only)"
} else {
    Write-Warning "no extra_model_paths.yaml at $liveYaml -- the new instance will see no models"
}

# --- custom node packs, pinned to the live SHAs ---------------------------------------------------
# Remotes are read off the LIVE checkouts rather than hardcoded -- a hardcoded guess was wrong for
# ComfyUI-ClownSampler (it is rdanalex/, not ClownsharkBatwing/), and the live install is the only
# authority on where each pack actually came from.
$customDir = Join-Path $comfyDir "custom_nodes"
New-Item -ItemType Directory -Force -Path $customDir | Out-Null

$livePacks = Get-ChildItem -Path (Join-Path $LiveRoot "custom_nodes") -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName ".git") }

$pinned = @{}
foreach ($pack in $livePacks) {
    $name = $pack.Name
    $livePack = $pack.FullName
    $url = (git -C $livePack remote get-url origin).Trim()
    if (-not $url) {
        Write-Warning "live pack $name has no origin remote; skipping"
        continue
    }
    $sha = (git -C $livePack rev-parse HEAD).Trim()
    $pinned[$name] = @{ url = $url; sha = $sha }
    $dest = Join-Path $customDir $name
    if (-not (Test-Path (Join-Path $dest ".git"))) {
        Say "cloning $name @ $($sha.Substring(0,7)) from $url"
        git clone --quiet $url $dest
        if (-not (Test-Path (Join-Path $dest ".git"))) {
            Write-Warning "clone failed for $name ($url) -- skipping"
            $pinned.Remove($name)
            continue
        }
    }
    git -C $dest fetch --quiet origin $sha 2>&1 | Out-Null
    git -C $dest checkout --quiet $sha
}
$pinned | ConvertTo-Json | Set-Content (Join-Path $Root "pinned_custom_nodes.json") -Encoding utf8
Say "pinned $($pinned.Count) packs to the live SHAs (core is the only variable)"

if ($SkipVenv) { Say "SkipVenv set -- stopping before the venv build"; exit 0 }

# --- isolated venv ---------------------------------------------------------------------------------
if (-not (Test-Path $venvPy)) {
    Say "creating isolated venv at $venvDir"
    & "C:\Program Files\Python312\python.exe" -m venv $venvDir
}
Say "upgrading pip"
& $venvPy -m pip install --quiet --upgrade pip setuptools wheel

Say "installing torch 2.10.0+cu128 (matches the working card config)"
& $venvPy -m pip install --quiet torch==2.10.0 torchvision==0.25.0 torchaudio==2.10.0 `
    --index-url https://download.pytorch.org/whl/cu128

Say "installing ComfyUI requirements"
& $venvPy -m pip install --quiet -r (Join-Path $comfyDir "requirements.txt")

# kornia is PINNED on the live install; an unpinned resolve broke the Jul core once.
Say "pinning kornia==0.8.2 (live install's pin)"
& $venvPy -m pip install --quiet "kornia==0.8.2"

# Pack requirements install WITH their dependencies, but under a constraints file that pins the
# torch stack. Doc 25 says "--no-deps where a pack would drag torch"; applying --no-deps blanket
# is too blunt -- it silently dropped wcwidth (WanVideoWrapper), pyparsing (RES4LYF) and
# matplotlib's fonttools/kiwisolver/python-dateutil, and the packs then failed to import for
# reasons that look exactly like a core incompatibility. Constraints give the real fix: everything
# resolves normally, torch simply cannot move.
$constraints = Join-Path $Root "torch-constraints.txt"
@(
    "torch==2.10.0"
    "torchvision==0.25.0"
    "torchaudio==2.10.0"
    "kornia==0.8.2"
) | Set-Content $constraints -Encoding ascii

# SageAttention, and the triton it needs. The live venv has both; a staged venv built by this
# script did NOT, so a cutover would have silently lost a measured +25% on video. Nothing would
# have crashed -- comfy_launch_policy refuses to pass --use-sage-attention to an interpreter
# without the package, so it degrades to sdpa -- which is precisely why the gap survived: the
# failure mode is a quiet capability loss, not an error. Under constraints so neither can move
# torch. Versions match the live install.
Say "installing sageattention + triton-windows (the launch policy needs them to offer sage)"
& $venvPy -m pip install --quiet -c $constraints "triton-windows==3.7.1.post27" "sageattention==1.0.6"

foreach ($name in $pinned.Keys) {
    $req = Join-Path $customDir "$name\requirements.txt"
    if (Test-Path $req) {
        Say "installing requirements for $name (torch pinned via constraints)"
        & $venvPy -m pip install --quiet -c $constraints -r $req
    }
}

Say "venv ready: $venvPy"
& $venvPy -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
foreach ($p in @("sageattention","triton-windows")) {
    $v = & $venvPy -m pip show $p 2>$null | Select-String "^Version:"
    if ($v) { Say "  $p $($v -replace 'Version: ','')" } else { Say "  $p MISSING -- sage attention will not be offered" }
}

if ($Launch) {
    Say "launching on :$Port (PYTHONUTF8=1 required -- the Jul core's RES4LYF crashes stderr logging without it)"
    $env:PYTHONUTF8 = "1"
    Start-Process -FilePath $venvPy `
        -ArgumentList @("$comfyDir\main.py", "--listen", "127.0.0.1", "--port", "$Port") `
        -WorkingDirectory $comfyDir
    Say "health-check with: curl -s http://127.0.0.1:$Port/system_stats"
}
