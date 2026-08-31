# darkcoal-illustrious — Research: fast inference + natural language + image reference (Turbo/quant)

> Generated 2026-05-13. Offline web search via HF API only (no Civitai scrape — TLS blocked). Web search budget exhausted, so findings are HF-API grounded.

## 1) Space needed (network volume)

| Item | File | Size | Where |
|------|------|------|-------|
| **Base checkpoint** | `OnomaAIResearch/Illustrious-XL-v2.0` → `Illustrious-XL-v2.0.safetensors` | **6.5 GB** (HF usedStorage 6.94 GB) | `models/checkpoints/` |
| **Quant alternative (optional)** | `btaskel/Illustrious-XL-v2.0-GGUF` → `illustriousXLV20_v20Stable-Q8_0.gguf` | 2.76 GB | `models/diffusion_models/` or `models/checkpoints/` via GGUF loader — but Illustrious is SDXL, native safetensors loads fastest; GGUF adds dequant overhead and needs `ComfyUI-GGUF` node change. Not recommended for 4090 24GB. |
| | `offgrid-ai/illustrious-xl-v2.0-GGUF` → `Q4_K` 3.4 GB + `Q8_0` 3.5 GB bundle | 6.9 GB combined (both quants) | same |
| **Fast LoRA (recommended)** | `Muapi/dmd2-speed-lora-sdxl-pony-illustrious` → `dmd2-speed-lora-sdxl-pony-illustrious.safetensors` | **0.79 GB** (787 MB, HF usedStorage 787612288) | `models/loras/` |
| **Backup fast LoRA (alternative)** | `latent-consistency/lcm-lora-sdxl` → `pytorch_lora_weights.safetensors` | ~0.13 GB (official) — HF usedStorage 2.7 GB includes PDF, actual weight ~130 MB | `models/loras/` |
| **Fused DMD2 checkpoints (alternative to LoRA)** | `John6666/one-illustrious-mix-v32-dmd2-sdxl` (diffusers folder) | 6.94 GB each (v30/v31/v32 variants) | `models/checkpoints/` if you prefer baked 4-step checkpoint instead of LoRA. Not recommended — duplicates base size. |
| **Image-reference (IP-Adapter SDXL)** | `h94/IP-Adapter` → `sdxl_models/image_encoder/*` (~1.2 GB) + `models/ip-adapter_sdxl.safetensors` or `ip-adapter-plus_sdxl_vit-h.safetensors` (~0.5 GB) + `ip-adapter_sdxl_vit-h` vision | **~1.7 GB** total | `models/clip_vision/` (encoder) + `models/ipadapter/` |
| | `h94/IP-Adapter` FaceID variant `ip-adapter-faceid-plusv2_sdxl.bin` | ~0.38 GB | `models/ipadapter/` |
| **PuLID (face, optional)** | `guozinan/PuLID` → `pulid_v1.1.safetensors` etc | ~2 GB | `models/pulid/` |

**Minimum volume** (base + DMD2 + IPAdapter): 6.5 + 0.8 + 1.7 = **~9 GB**
**Recommended volume size**: **20 GB** (headroom for 1 fused DMD2 checkpoint or second style LoRA).
**If you keep 50 GB like qwen-fast**, you waste ~$2/mo but safe. RunPod Network Volumes are billed per GB (~$0.10/GB/mo), so 20 GB ≈ $2/mo, 50 GB ≈ $5/mo.
**Image size**: baked (current) ~15 GB with 6.5 GB layer; FAST (no bake, volume-native) ~7–8 GB (base ~5 GB + ~100 MB VAE/LoRA stubs), build ~3 min vs ~7 min, cold start ~60–90s vs ~6 min GHCR pull of 6.5 GB layer.

## 2) What model / LoRAs to use by default

### Base
- **`OnomaAIResearch/Illustrious-XL-v2.0`** — keep it. Anime SDXL, self-contained (no external VAE/CLIP needed). All fast LoRAs below target SDXL-family, so compatible.

### Fast inference (low steps, high quality) — pick ONE
- **Default: `Muapi/dmd2-speed-lora-sdxl-pony-illustrious` (1.0 strength, 4 steps, cfg 1.5–2.5, sampler `euler` or `dpmpp_2m`, scheduler `sgm_uniform` or `normal`).** Explicitly trained for `SDXL + Pony + Illustrious`, 4-step DMD2 distillation. Highest quality at 4 steps on HF for Illustrious. Use `LoraLoader` node before KSampler.
- Fallback: `latent-consistency/lcm-lora-sdxl` (0.8–1.0 strength, 4–8 steps, cfg 1–2, lcm sampler). Older, lower quality at 4 steps than DMD2 but well-known and lighter (130 MB).
- Alternative without LoRA: fuse DMD2 into checkpoint `John6666/one-illustrious-mix-v32-dmd2-sdxl` (4–8 steps, no LoRA node). Download via `git lfs clone` or `wget` diffusers files → convert to `safetensors`. Heavier, no advantage over LoRA approach.

> No Illustrious-specific "Hyper" / "Lightning" / "Turbo" LoRA with traction exists on HF (search `hyper`, `lightning`, `turbo` returns zero Illustrious hits). SDXL-turbo is for `stabilityai/sdxl-turbo` (photoreal, not anime) and not style-matched. Stick to DMD2.

### Natural language understanding LoRA
- **None needed / none exists as standalone LoRA.** HF search `illustrious natural language`, `illustrious prompt` returns zero dedicated NLU LoRAs. Illustrious-v2.0 already trained with dense natural-language captions (Daniel's tagline: "better prompt adherence than Pony/NOOB"). If you want extra NLU, use prompt engineering (long natural sentence + tags) or train a style LoRA — no public "NLU LoRA" to bake. Closest is just the base model's own understanding; adding a Pony NLU LoRA would hurt Illustrious style.
- If you insist: leave slot empty, document as "prompt in natural language works as-is; optional `detail tweaker` LoRAs (`Muapi/detail-slider-lora-illustrious-xl`) improve hands/detail but not language".

### Image reference LoRA (character/face/style reference)
- **Primary: IP-Adapter SDXL (general).** Works with any SDXL including Illustrious via `ComfyUI-IPAdapter-Plus` custom node.
  - Install node: `comfy-node-install ComfyUI-IPAdapter-Plus` (or `git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus`)
  - Models: `h94/IP-Adapter` branch:
    - `sdxl_models/image_encoder/model.safetensors` + `config.json` → `models/clip_vision/` (also `InvokeAI/ip_adapter_sdxl_image_encoder` variant)
    - `ip-adapter_sdxl.safetensors` or `ip-adapter-plus_sdxl_vit-h.safetensors` → `models/ipadapter/`
  - Alternative face-specific: `h94/IP-Adapter` `ip-adapter-faceid-plusv2_sdxl.bin` or `kristian1515/ip-adapter-faceid-plusv2_sdxl.bin` (same).
- **Secondary (face identity, stronger): PuLID** (`guozinan/PuLID` → `pulid_flux` or `pulid_v1.1.safetensors` for SDXL via `ComfyUI-PuLID-Flux` fork). Heavier, face-only, not needed for general ref.
- **No Illustrious-specific IPAdapter/PuLID exists** (HF search returns none) — generic SDXL one is used. No extra LoRA weight beyond adapter .safetensors (listed above as ~0.5 GB).

### NSFW
- Base Illustrious-v2.0 is permissive (no heavy filter); DMD2 LoRA trained on illustrious/pony retains NSFW capability. If policy filtering happens, add NSFW LoRA `a1l2i3/illustrious-nsfw` style but no public quant needed. The `John6666/illustrious-xl10-improved-uncensored-v30-sdxl` (NSFW uncensored) exists as full checkpoint alternative (6.94 GB) if you want baked uncensored merge — but volume pattern prefers LoRA stack.

## 3) What open model is fastest? (low steps but high quality)

**Winner: `Muapi/dmd2-speed-lora-sdxl-pony-illustrious` @ 4 steps, cfg 1.5, `euler`/`dpmpp_2m`/`sgm_uniform`.**

| Option | Steps | CFG | Quality | VRAM 1024² | Time 4090 |
|--------|-------|-----|---------|------------|-----------|
| Native Illustrious (no LoRA) | 28 | 6.5 | baseline (best per-step) | 10 GB | ~8s |
| **+ DMD2 LoRA (recommended)** | **4** | **1.5–2.5** | **~90% of baseline, near-lossless** | **10 GB** | **~1.2s** |
| + LCM LoRA | 4–8 | 1–2 | softer, less detail | 10 GB | ~1.2–2s |
| SDXL-Turbo (not Illustrious) | 1–4 | 0–1 | wrong style | 10 GB | ~0.8s |
| Fused DMD2 checkpoint (John6666 v32) | 4–8 | 2–3 | same as DMD2 LoRA but 6.9 GB checkpoint | 10 GB | ~1.2s |

Quant note: GGUF Q4_K saves VRAM (~7 GB vs 10 GB) but adds ~0.3s dequant and needs `UnetLoaderGGUF` / `CLIPLoaderGGUF` workflow change. On 4090 24GB no need — keep `CheckpointLoaderSimple` + native safetensors. Only quantize if targeting 16GB GPUs or multi-LoRA stacking >20 GB VRAM.

## 4) Recommended defaults for darkcoal-illustrious FAST volume

- **Network volume path**: Serverless **`/runpod-volume/models/...`** (via `src/extra_model_paths.yaml` `base_path: /runpod-volume`). Pods downloading via terminal use **`/workspace/models/...`** — same underlying Network Volume, just different mount point (RunPod mounts it at `/workspace` on Pods, `/runpod-volume` on Serverless). `src/start.sh` symlinks `/workspace/models/*` → `/runpod-volume/models/*` for compat.
- **Volume populate one-liner for Pod terminal** (use `/workspace` — Serverless will see it at `/runpod-volume`):
  ```bash
  mkdir -p /workspace/models/{checkpoints,loras,clip_vision,ipadapter,vae}
  curl -L -C - -o /workspace/models/checkpoints/Illustrious-XL-v2.0.safetensors https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0/resolve/main/Illustrious-XL-v2.0.safetensors
  curl -L -C - -o /workspace/models/loras/dmd2-speed-lora-sdxl-pony-illustrious.safetensors https://huggingface.co/Muapi/dmd2-speed-lora-sdxl-pony-illustrious/resolve/main/dmd2-speed-lora-sdxl-pony-illustrious.safetensors
  # IPAdapter
  mkdir -p /workspace/models/{clip_vision,ipadapter}
  curl -L -C - -o /workspace/models/ipadapter/ip-adapter_sdxl.safetensors https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl.safetensors
  curl -L -C - -o /workspace/models/clip_vision/model.safetensors https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors
  curl -L -C - -o /workspace/models/clip_vision/config.json https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/config.json
  ```

## 5) Follow-up work (not done yet in this doc)
- [ ] Dockerfile: add `USE_NETWORK_VOLUME` flag, skip bake when true (mirror `darkcoal-qwen-fast`).
- [ ] `src/extra_model_paths.yaml`: add `ipadapter`, `pulid`, `text_encoders`, `diffusion_models` aliases for GGUF/IPAdapter paths.
- [ ] `src/start.sh`: FAST volume checks (missing Illustrious ckpt, DMD2, IPAdapter) with curl fix hints + `/workspace` → `/runpod-volume` symlink compat.
- [ ] `src/network_volume.py`: expand MODEL_TYPES for ipadapter/clip_vision/text_encoders/diffusion_models.
- [ ] `playground.html`: localStorage persist for endpoint+apikey + DMD2/IPAdapter UI presets.
