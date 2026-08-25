# darkcoal-illustrious — RunPod quickstart (4090 24GB)

Image (GHCR, built on push to main):
  ghcr.io/alfa-jim/darkcoal-illustrious:latest
  ghcr.io/alfa-jim/darkcoal-illustrious:illustrious

Baked model: OnomaAIResearch/Illustrious-XL-v2.0 -> models/checkpoints/Illustrious-XL-v2.0.safetensors (~6.5GB)
VRAM @1024x1024: ~10GB — fits 4090 comfortably.

1) Make GHCR package public once:
   github.com/Alfa-jim/darkcoal-illustrious -> right sidebar Packages -> darkcoal-illustrious -> Package settings -> Change visibility -> Public
   (GHCR is private on first push, RunPod can't pull until public, or add GHCR creds to the template.)

2) RunPod Template:
   Container Image = ghcr.io/alfa-jim/darkcoal-illustrious:latest
   Container Disk  = 25 GB
   GPU             = ADA_24 / 4090 24GB, 1x, CUDA 12.8+
   Expose HTTP 8188 if you want ComfyUI UI (optional), or just use the RunPod serverless handler.

3) Test (serverless /runsync):
   Use test_input.json in repo root, or test_resources/workflows/workflow_illustrious.json.
   Any SDXL workflow that CheckpointLoaderSimple -> Illustrious-XL-v2.0.safetensors works.

4) Local quick test:
   docker buildx build --platform linux/amd64 --target final --build-arg MODEL_TYPE=illustrious -t darkcoal-illustrious:local .
   docker run --gpus all -p 8188:8188 -p 8000:8000 darkcoal-illustrious:local
   # then POST to http://localhost:8000/runsync with test_input.json

Notes:
- Base image is nvidia/cuda:12.8.1 (allowedCudaVersions 12.8/12.9/13.0 in .runpod/hub.json).
- No extra VAE/CLIP downloads needed — Illustrious checkpoint is self-contained SDXL.
- Default workflow is 1024x1024, 28 steps, cfg 6.5, euler_ancestral/normal — tune in your request JSON.
