$objectInfo = Invoke-RestMethod http://127.0.0.1:8188/object_info

Write-Host "WanVideoSampler scheduler choices:" -ForegroundColor Cyan
$objectInfo.WanVideoSampler.input.required.scheduler[0]

Write-Host "`nWanVideoSampler sampler choices:" -ForegroundColor Cyan
if ($objectInfo.WanVideoSampler.input.required.sampler_name) {
    $objectInfo.WanVideoSampler.input.required.sampler_name[0]
} elseif ($objectInfo.WanVideoSampler.input.required.sampler) {
    $objectInfo.WanVideoSampler.input.required.sampler[0]
} else {
    "No sampler_name/sampler enum exposed in required inputs."
}

Write-Host "`nWAN T5 text encoder choices:" -ForegroundColor Cyan
$objectInfo.LoadWanVideoT5TextEncoder.input.required.model_name[0]
