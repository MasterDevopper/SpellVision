# T3/T5 metadata sourcing research (2026-09-15)
[V]=verified this session, [I]=inferred.

## CivitAI API v1 (docs: https://developer.civitai.com/site/reference/) [V]
- GET /api/v1/model-versions/by-hash/{hash}: PUBLIC, accepts AutoV1/AutoV2/AutoV3/SHA256/BLAKE3/CRC32 case-insensitive; same object as /model-versions/{id}. Bulk POST by-hash (<=100 SHA256) and by-hash/ids (<=10000). /model-versions/mini/{id}.
- Version object: id, modelId, name, nsfwLevel, createdAt, updatedAt, status, publishedAt, trainedWords, trainingStatus, trainingDetails, baseModel, baseModelType, description, uploadType, usageControl, licensingFee, paidAccess, air, stats, model{name,type,nsfw,poi}, files[]{id,sizeKB,name,type,pickle/virus scans,metadata{fp,size,format},hashes{AutoV1,AutoV2,SHA256,CRC32,BLAKE3,SHA256_12},primary,downloadUrl}, images[] (filtered by browsing level), downloadUrl.
- images[].meta UNDOCUMENTED, A1111 infotext dump: prompt, negativePrompt, steps, sampler ("DPM++ 2M Karras" — scheduler folded in, NO scheduler key), cfgScale, seed, Size, clipSkip, Model, Model hash, hashes, resources, Denoising strength, Hires*, ADetailer*. hasMeta:false common.
- GET /api/v1/models/{id}: PUBLIC. name, description HTML, allowNoCredit/CommercialUse/Derivatives/DifferentLicense, type, nsfw, nsfwLevel, availability, creator, tags, modelVersions[]. List: limit<=100, cursor (page*limit>1000 -> 429), query, tag, types, baseModels, nsfw, browsingLevel.
- Auth: Authorization: Bearer; reads public in 2026; DOWNLOADS ALWAYS need token (401 anon even for public files); early access needs entitled account. Rate limits unpublished; design for 429 + jittered backoff.
- NSFW bitmask PG=1 PG13=2 R=4 X=8 XXX=16 Blocked=32; browsingLevel=31.
- STRUCTURED recommended-settings field: NONE (confirmed). Sources = images[].meta (mode when >=3) + description prose regex (clip skip, N steps / N-M steps, cfg, weight ranges, sampler names, resolution). Low confidence.

## civitai.red / green / black [V]
- civitai.red = OFFICIAL Civitai domain since 2026-04-15: civitai.com = SFW-only front door, civitai.red = SFW+NSFW + crypto; same DB/accounts. civitai.green -> 301 civitai.com. civitai.black does not exist.
- API "remains on civitai.com and is accessible through civitai.red"; /api/v1 identical on both hosts; mature previews only with browsingLevel/nsfw=true + key on allowed account. Keep base https://civitai.com/api/v1, host configurable, never hardcode .red.

## HuggingFace [V]
- GET /api/models/{repo}: id, author, sha, private, gated, pipeline_tag, library_name, tags, cardData (README frontmatter), siblings, config, safetensors, lastModified. siblings[] {rfilename} only; ?blobs=true adds blobId,size,lfs{sha256,size}. model_info(files_metadata=True) same. NO by-hash lookup on HF -> local sha256->(repo,path) index from known repos + filename heuristics.
- Frontmatter: license(+license_name/link), base_model (str|list), base_model_relation (adapter|finetune|quantized|merge), library_name diffusers, pipeline_tag, tags, instance_prompt (trigger; convention), inference.parameters{width,height}, widget[{text, output.url}] example outputs.
- Recommended settings: diffusers snippet kwargs most reliable: regex (num_inference_steps|guidance_scale|true_cfg_scale|shift|max_sequence_length|num_frames|fps|height|width)\s*=\s*([\d.]+); prose fallback.
- Download resolve/{rev}/{path} with Bearer; hf_hub_download handles cache/ETag/429. Rate limits per 5 min: anon 500 API/3000 resolvers; free 1000/5000; PRO 2500/12000. Always send token.

## Prior art sidecars [V]
- Lora-Manager <file>.metadata.json: file_name, model_name, file_path, size, modified, sha256, autov3, hash_status, base_model, preview_url, preview_nsfw_level, notes, favorite, exclude, db_checked, civitai_deleted, from_civitai, metadata_source, last_checked_at, tags, modelDescription, model_type, civitai{raw version + model + creator + customImages[]}, usage_tips JSON string {strength,strength_min,strength_max,strength_range,clip_strength,clip_skip} (user/heuristic), _unknown_fields. Recipes models/loras/recipes/{id}.recipe.json.
- InvokeAI default_settings: MainModelDefaultSettings{vae, vae_precision, scheduler, steps, cfg_scale, cfg_rescale_multiplier, width, height, guidance, cpu_only, fp8_storage}; LoRA {weight,weight_min,weight_max}; trigger_phrases; cover_image; source_api_response. Closest analogue.
- SwarmUI: modelspec.* safetensors header (title, description, thumbnail, trigger_phrase, usage_hint, resolution, prediction_type, license, architecture) or <model>.swarm.json; standard_width/height, lora_default_weight. No per-model steps/cfg.
- Stability Matrix <model>.cm-info.json: CivitAI dump + InferenceDefaults{Sampler, Scheduler, Steps, CfgScale, Width, Height}; <model>.preview.jpeg.

## Family seed table (official)
| Family | Steps | CFG | Shift | Sampler/sched | Res/frames/fps |
| FLUX.1-dev | 50 (Comfy 20) | guidance 3.5 cfg 1 | – | euler/simple | 1024² |
| Krea 2 Turbo | 8 (min 4) | cfg 1 | 1.15 | euler/simple | 1024² |
| Krea 2 Raw | 52 | 3.5 | – | – | 1024² |
| Z-Image-Turbo | 8–9 | cfg 1 | 3 | res_multistep/simple | 1024² |
| Qwen-Image | 50 | true_cfg 4 | 3.1 | euler/simple | 1328² |
| Wan 2.2 T2V-A14B | 40 | high 4.0 / low 3.0 | 12, boundary 0.875 | – | 81f@16 480/720p |
| Wan 2.2 I2V-A14B | 40 | 3.5/3.5 | 5.0 boundary 0.9 | – | 81f@16 |
| Wan 2.2 TI2V-5B | 50 | 5.0 | 5.0 | – | 121f@24 1280x704 |
| Wan 2.2 lightx2v LoRA | 4 (2+2) | 1 | 5 | euler/simple | 81f@16 |
| LTX-2.3 distilled | 8 (+4 stage2) | 1 | – | euler + ManualSigmas | ÷32, 8n+1, 24fps (audio 25) |
| LTX-2.3 dev | 20–40 [I] | 3–4 [I] | – | euler | same |
| HunyuanVideo | 50 (Comfy 20) | embedded 6.0 cfg 1 | flow 7.0 | – | 129f 720x1280 24fps [I fps] |
| Mochi 1 | 64 | 4.5 | – | – | 848x480 84f@30 |
| SD3.5 Large / Turbo | 28 / 4 | 3.5–4.5 / 0 | – | – | 1024² |
| PixArt-Σ | 20 | 4.5 | – | DPM | 1024² bins |
| Lumina 2 | 50 (Comfy 30–40) | 4.0 trunc 0.25 | t_shift 6 | euler | 1024² |
| Anima | 30–50 | 4–5 | – | er_sde/euler_a simple | 512²–1536² |
| SDXL Lightning N | N | 0 | – | euler sgm_uniform | 1024² |

## Proposed sidecar <model>.spellvision.json (schema spellvision.model-sidecar/1)
identity{file_name,size,hashes{sha256,autov2,blake3,crc32},hash_status,kind,family{value,provenance},sources[{site,host,model_id,version_id,url,fetched_at,browsing_level,raw_cache}|{site:huggingface,repo,path,revision,fetched_at}]}
display{name{value,user_override},description_html{…},creator,license{spdx,name,allow*,provenance},nsfw_level,trigger_words{value,provenance,user_override},images[{origin_url,local_path,width,height,nsfw_level,is_cover,user_override,meta{…}}]}
recommended{steps,sampler,scheduler,cfg,guidance,shift,clip_skip,width,height,aspect_hint,frames,fps,lora_strength{value,min,max},negative_prompt,prompt_prefix} each {value,provenance,confidence,n}
user{notes,favorite}, _unknown_fields.
Provenance enum: site:image-meta-mode, site:description-regex, site:trainedWords/site:baseModel/site:model, card:frontmatter, card:snippet-regex, card:prose-regex, table:family-default, user.
Resolution: user > site:image-meta-mode > card:snippet-regex > site:description-regex/card:prose-regex > table:family-default. Cache raw site JSON beside sidecar; refetch on age; 401 on download -> "key required" prompt once.
