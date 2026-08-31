#!/usr/bin/env bash

# Start SSH server if PUBLIC_KEY is set
if [ -n "$PUBLIC_KEY" ]; then
    mkdir -p ~/.ssh
    echo "$PUBLIC_KEY" > ~/.ssh/authorized_keys
    chmod 700 ~/.ssh
    chmod 600 ~/.ssh/authorized_keys
    for key_type in rsa ecdsa ed25519; do
        key_file="/etc/ssh/ssh_host_${key_type}_key"
        if [ ! -f "$key_file" ]; then
            ssh-keygen -t "$key_type" -f "$key_file" -q -N ''
        fi
    done
    service ssh start && echo "worker-comfyui: SSH server started" || echo "worker-comfyui: SSH server could not be started" >&2
fi

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

# Pod vs Serverless mount: Pod terminal is /workspace, Serverless mounts same
# Network Volume at /runpod-volume. ComfyUI reads /runpod-volume via
# extra_model_paths.yaml, so if /workspace has models we symlink them into
# /runpod-volume for consistency. Also handle the reverse (serverless-only).
if [ ! -d /runpod-volume/models ] && [ -d /workspace/models ]; then
    echo "worker-comfyui: Pod compat — /workspace/models found, symlinking into /runpod-volume" >&2
    mkdir -p /runpod-volume
    for d in /workspace/models/*; do
        bn=$(basename "$d")
        if [ ! -e "/runpod-volume/models/$bn" ]; then
            ln -s "$d" "/runpod-volume/models/$bn" 2>/dev/null || true
        fi
    done
    if [ ! -e /runpod-volume/models ] && [ -d /workspace/models ]; then
        ln -s /workspace/models /runpod-volume/models 2>/dev/null || true
    fi
fi

# ---------------------------------------------------------------------------
# GPU pre-flight check
# ---------------------------------------------------------------------------
echo "worker-comfyui: Checking GPU availability..."
if ! GPU_CHECK=$(python3 -c "
import torch
try:
    torch.cuda.init()
    name = torch.cuda.get_device_name(0)
    cap = torch.cuda.get_device_capability(0)
    _ = (torch.zeros(8, device='cuda') + 1).sum().item()
    torch.cuda.synchronize()
    print(f'OK: {name} (sm_{cap[0]}{cap[1]}), torch {torch.__version__}, cuda {torch.version.cuda}')
except Exception as e:
    print(f'FAIL: {e}')
    exit(1)
" 2>&1); then
    echo "worker-comfyui: GPU is not available or incompatible with this PyTorch build:"
    echo "worker-comfyui: $GPU_CHECK"
    exit 1
fi
echo "worker-comfyui: GPU available — $GPU_CHECK"

# Ensure ComfyUI-Manager runs in offline network mode inside the container
comfy-manager-set-mode offline || echo "worker-comfyui - Could not set ComfyUI-Manager network_mode" >&2

# ── FAST: network volume checks (only when USE_NETWORK_VOLUME=true, default) ──
# In darkcoal-illustrious FAST, Illustrious-XL-v2.0 + DMD2 + IPAdapter live on /runpod-volume,
# NOT baked. This cuts image from ~14 GB -> ~7 GB and cold start from ~6 min -> ~60s.
# VAE is self-contained (no external VAE needed). Set USE_NETWORK_VOLUME=false to bake.
if [ "${USE_NETWORK_VOLUME:-true}" = "true" ]; then
  if [ ! -d /runpod-volume ]; then
    echo "worker-comfyui: FATAL — /runpod-volume does not exist (network volume NOT attached)." >&2
    echo "worker-comfyui: Fix: RunPod Console → Serverless → endpoint → Manage → Edit → Advanced → Network Volume → select illustrious-models → Save (same region as endpoint)." >&2
    echo "worker-comfyui: Continuing anyway (ComfyUI will 400 until volume attached)." >&2
  elif ! mount 2>/dev/null | grep -q " /runpod-volume " && ! df /runpod-volume >/dev/null 2>&1; then
    echo "worker-comfyui: WARNING — /runpod-volume exists but not a mount (empty container dir?). df:" >&2
    df -h /runpod-volume 2>&1 | sed 's/^/worker-comfyui:   /' || true
  fi

  MISSING=""
  for f in "/runpod-volume/models/checkpoints/Illustrious-XL-v2.0.safetensors"; do
    [ -f "$f" ] || MISSING="$MISSING $f"
  done
  if [ -n "$MISSING" ]; then
    echo "worker-comfyui: WARNING — USE_NETWORK_VOLUME=true but missing on /runpod-volume:$MISSING" >&2
    echo "worker-comfyui: FAST image does not bake the checkpoint — populate the volume:" >&2
    echo 'worker-comfyui:   mkdir -p /runpod-volume/models/checkpoints /runpod-volume/models/loras /runpod-volume/models/ipadapter /runpod-volume/models/clip_vision' >&2
    echo 'worker-comfyui:   # Pod mount may be /workspace — same data; use /runpod-volume on serverless.' >&2
    echo 'worker-comfyui:   curl -L -C - -o /runpod-volume/models/checkpoints/Illustrious-XL-v2.0.safetensors https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0/resolve/main/Illustrious-XL-v2.0.safetensors' >&2
    echo 'worker-comfyui:   # Optional turbo (4-step, recommended):' >&2
    echo 'worker-comfyui:   curl -L -C - -o /runpod-volume/models/loras/dmd2-speed-lora-sdxl-pony-illustrious.safetensors https://huggingface.co/Muapi/dmd2-speed-lora-sdxl-pony-illustrious/resolve/main/dmd2-speed-lora-sdxl-pony-illustrious.safetensors' >&2
    echo 'worker-comfyui:   # Optional image ref (IPAdapter SDXL):' >&2
    echo 'worker-comfyui:   curl -L -C - -o /runpod-volume/models/ipadapter/ip-adapter_sdxl.safetensors https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter_sdxl.safetensors' >&2
    echo 'worker-comfyui:   curl -L -C - -o /runpod-volume/models/clip_vision/model.safetensors https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors' >&2
    echo 'worker-comfyui:   curl -L -C - -o /runpod-volume/models/clip_vision/config.json https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/config.json' >&2
  else
    echo "worker-comfyui: FAST volume check OK — Illustrious-XL-v2.0 present on /runpod-volume"
    ls -lh /runpod-volume/models/checkpoints/Illustrious-XL-v2.0.safetensors 2>&1 | sed 's/^/worker-comfyui:   /'
    for opt in "/runpod-volume/models/loras/dmd2-speed-lora-sdxl-pony-illustrious.safetensors" "/runpod-volume/models/ipadapter/ip-adapter_sdxl.safetensors"; do
      [ -f "$opt" ] && ls -lh "$opt" 2>&1 | sed 's/^/worker-comfyui:   + /' || echo "worker-comfyui:   (optional) $opt not present — ok" | sed 's/^/worker-comfyui:   /'
    done
  fi

  if [ ! -f /comfyui/extra_model_paths.yaml ]; then
    echo "worker-comfyui: FATAL — /comfyui/extra_model_paths.yaml missing (build bug)." >&2
  else
    echo "worker-comfyui: extra_model_paths.yaml present:"; sed 's/^/worker-comfyui:   /' /comfyui/extra_model_paths.yaml 2>&1
  fi

  if [ ! -d /comfyui/custom_nodes/ComfyUI_IPAdapter_plus ] && [ ! -d /comfyui/custom_nodes/ComfyUI-IPAdapter-Plus ]; then
    echo "worker-comfyui: NOTE — IPAdapter custom node not baked; image-ref workflows will fail until baked or volume provides it. See Dockerfile." >&2
  else
    echo "worker-comfyui: IPAdapter node present"
  fi
fi

echo "worker-comfyui: Starting ComfyUI"

: "${COMFY_LOG_LEVEL:=DEBUG}"
COMFY_PID_FILE="/tmp/comfyui.pid"

if [ "$SERVE_API_LOCALLY" == "true" ]; then
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --listen --verbose "${COMFY_LOG_LEVEL}" --log-stdout &
    echo $! > "$COMFY_PID_FILE"
    echo "worker-comfyui: Starting RunPod Handler"
    python -u /handler.py --rp_serve_api --rp_api_host=0.0.0.0
else
    python -u /comfyui/main.py --disable-auto-launch --disable-metadata --verbose "${COMFY_LOG_LEVEL}" --log-stdout &
    echo $! > "$COMFY_PID_FILE"
    echo "worker-comfyui: Starting RunPod Handler"
    python -u /handler.py
fi
