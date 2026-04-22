$latest = Get-ChildItem "D:\AI_ASSETS\comfy_runtime\ComfyUI\output" -Filter "*native_prompt_api.json" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

if (-not $latest) {
  Write-Error "No *_native_prompt_api.json files found."
  exit 1
}

Write-Host "Prompt: $($latest.FullName)"
Write-Host "LastWriteTime: $($latest.LastWriteTime)"

$prompt = Get-Content $latest.FullName | ConvertFrom-Json

$prompt.PSObject.Properties |
  ForEach-Object {
    [PSCustomObject]@{
      NodeId = $_.Name
      ClassType = $_.Value.class_type
    }
  } |
  Format-Table -AutoSize
