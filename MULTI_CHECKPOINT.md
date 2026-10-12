# Shirea / NXT checkpoint selection

The playground selects Shirea 2D v1.0 or IllustriousNXT XL v2.0 for each generation. Shirea is the initial default. Both are Illustrious `.safetensors` checkpoints. The optional original Illustrious XL v2.0 choice requires its existing file on the volume; the new installer does not download it.

Checkpoint selection and optional DMD2 V7.5 FIX settings persist in `illustrious.settings.v2`. Refreshing restores controls without submitting a job. Named presets also capture these settings. The RunPod API retains its existing `{input: {workflow, images}}` format: checkpoint selection is `CheckpointLoaderSimple.inputs.ckpt_name`, and enabled LoRAs are chained through `LoraLoader`. Custom workflows remain available.

## CPU Pod installation

Attach the same network volume to a CPU Pod. Stop Pro workers before deleting their weights. With `/workspace` mounted, the following removes only known Qwen Pro assets (including partial downloads), retains Qwen Turbo and unrelated files, and installs both checkpoints, DMD2 FIX, and IPAdapter reference support:

```bash
curl -fL --retry 3 https://raw.githubusercontent.com/Alfa-jim/darkcoal-illustrious/main/DOWNLOAD_ON_CPU_POD.sh -o /tmp/illustrious-models.sh && MODEL_VOLUME_ROOT=/workspace REMOVE_QWEN_PRO=1 bash /tmp/illustrious-models.sh
```

Omit `REMOVE_QWEN_PRO=1` to retain Pro. If Civitai requires authentication, enter a token without shell-history exposure:

```bash
read -rsp 'Civitai API token: ' CIVITAI_API_TOKEN; echo; export CIVITAI_API_TOKEN
```

Use an immutable commit in place of `main` for a reproducible installer. The standalone bootstrap embeds a pinned manifest and installer with checksum checks. It requires Python 3.11+, refuses an unmounted destination, shows an explicit Pro removal inventory, resumes `.part` files, verifies exact byte sizes and SHA256 before promotion, and prints progress once per second including during stalls and verification. Corrupt existing finalized files are preserved and cause a failure; move them aside before retrying. Completion is recorded as `/workspace/models/illustrious-manifest.json`.

## Storage

The six required files total **19,126,589,453 bytes (19.13 GB)**, including the 3.69 GB CLIP vision encoder. With the existing Turbo weights, the total is **30.45 GB**. Keep the shared network volume at **40 GB or more** after removing Pro. Retaining Pro as well needs over **45.08 GB**, before extra files and headroom. `df` on RunPod's network filesystem reports the storage pool, not your volume quota; check the configured quota in RunPod.

CPU Pod paths are `/workspace/models/{checkpoints,loras,ipadapter,clip_vision}`. Serverless sees the same files at `/runpod-volume/models/...`. No separate external VAE is required for these SDXL checkpoints. No heavy weights are baked into the default container.

## Sampling and deployment

DMD2 is initially disabled. Ordinary sampling starts at 28 steps / CFG 6.5 / Euler ancestral / Normal, all editable. The DMD2 starting-settings button enables V7.5 FIX at strength 1, 6 steps / CFG 1 / Euler / Normal. This is a practical starting point, not a guarantee of equal output quality. Disabling the toggle removes the LoRA but preserves the sampling controls; use the anime preset to restore ordinary sampling settings. Negative prompts have little or no effect at CFG 1.

The creator distinguishes V7.5 FIX from VISUAL ONLY and recommends more iterations (4â€“6) or lower CFG for difficult low-step results. See the [DMD2 model page](https://civitai.com/models/1850983). Checkpoint sources: [Shirea version 2570670](https://civitai.com/models/2284103?modelVersionId=2570670), [NXT version 2069051](https://civitai.com/models/1629360?modelVersionId=2069051). Exact file IDs and hashes are in `model-lock.json`.

Use the updated GHCR image, network volume attached, `USE_NETWORK_VOLUME=true`, one maximum worker, 50 GB container disk, and start with a 4090 / 24 GB GPU for 1024px single-image generation. Container disk is separate from the shared 40 GB model volume. Actual memory behavior with larger dimensions, batches, and reference conditioning requires a GPU acceptance test. Switching checkpoints triggers loading and may slow the next generation. No GPU inference is part of the CPU build smoke test.

Image references use the first upload through the pinned IPAdapter node; this does not replicate Qwen's ten-reference semantic mention system. The updated playground requires the updated worker for reference generation. IPAdapter is pinned to `a0f451a5113cf9becb0847b92884cb10cbdec0ef` and checked through ComfyUI's actual `/object_info` registry during Docker build.

## Validation

Run `node --test tests/model-options.test.cjs`, `node scripts/check_playground.cjs`, `python -m unittest discover -s tests -p test_download_checkpoints.py`, and `python scripts/make_download_command.py --check`. GitHub Actions runs these before building Linux AMD64 and publishing `latest`, `illustrious`, and the source-commit tag. The build smoke starts a private CPU ComfyUI process without model weights and verifies checkpoint, LoRA, sampler and reference node registration.

Live-browser verification covers checkpoint selection, DMD2 settings reaching workflow nodes, disabled DMD2 omission, saved strength after reload, and no generation on refresh. Additional regression tests cover symlinked Pro cleanup paths and button-driven persistence. Pro cleanup rejects symlinked files and directories before deleting anything. Output quality, checkpoint loading, GPU memory and reference adherence remain acceptance checks on the configured RunPod endpoint.

Commits marked `[assets-only]` run all tests but reuse the already published runtime image. CI verifies these commits do not alter the Dockerfile, worker source, dependencies, smoke test or runtime test input before skipping a redundant container build.
