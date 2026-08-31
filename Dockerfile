# Build argument for base image selection
ARG BASE_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

# Stage 1: Base image with common dependencies
FROM ${BASE_IMAGE} AS base

# Build arguments for this stage with sensible defaults for standalone builds
ARG COMFYUI_VERSION=0.29.0
ARG CUDA_VERSION_FOR_COMFY=12.8
ARG ENABLE_PYTORCH_UPGRADE=false
ARG PYTORCH_INDEX_URL

# Prevents prompts from packages asking for user input during installation
ENV DEBIAN_FRONTEND=noninteractive
# Prefer binary wheels over source distributions for faster pip installations
ENV PIP_PREFER_BINARY=1
# Ensures output from python is printed immediately to the terminal without buffering
ENV PYTHONUNBUFFERED=1
# Speed up some cmake builds
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Install Python, git and other necessary tools
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    git \
    wget \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    openssh-server \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip

# Clean up to reduce image size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Install uv (latest) using official installer and create isolated venv
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && ln -s /root/.local/bin/uvx /usr/local/bin/uvx \
    && uv venv /opt/venv

# Use the virtual environment for all subsequent commands
ENV PATH="/opt/venv/bin:${PATH}"

# Install comfy-cli + dependencies needed by it to install ComfyUI
RUN uv pip install comfy-cli==1.13.0 pip setuptools wheel

# Install ComfyUI
RUN if [ -n "${CUDA_VERSION_FOR_COMFY}" ]; then \
      /usr/bin/yes | comfy --workspace /comfyui install --version "${COMFYUI_VERSION}" --cuda-version "${CUDA_VERSION_FOR_COMFY}" --nvidia; \
    else \
      /usr/bin/yes | comfy --workspace /comfyui install --version "${COMFYUI_VERSION}" --nvidia; \
    fi

# Upgrade PyTorch if needed
RUN if [ "$ENABLE_PYTORCH_UPGRADE" = "true" ]; then \
      uv pip install --force-reinstall torch torchvision torchaudio --index-url ${PYTORCH_INDEX_URL}; \
    fi

RUN uv pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 \
      --index-url https://download.pytorch.org/whl/cu128 \
    && uv pip install -r /comfyui/requirements.txt \
    && for r in /comfyui/custom_nodes/*/requirements.txt; do \
         [ -f "$r" ] && uv pip install -r "$r" || true; \
       done \
    && uv pip install "transformers>=4.50.3,<5" "huggingface-hub<1.0"

# ── IPAdapter Plus (image reference) ──
# Needed for IPAdapterApply / LoadIPAdapter workflows (character/style ref).
# Lightweight; no model download here — models come from /runpod-volume.
RUN uv pip install insightface onnxruntime onnx 2>&1 | tail -5 || true
RUN comfy-node-install ComfyUI-IPAdapter-Plus 2>&1 | tail -20 || \
    (git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus /comfyui/custom_nodes/ComfyUI_IPAdapter_plus && \
     uv pip install -r /comfyui/custom_nodes/ComfyUI_IPAdapter_plus/requirements.txt 2>&1 | tail -10 || true)

# Re-apply deps after custom node install (node may have pulled conflicting torch/transformers)
RUN uv pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 \
      --index-url https://download.pytorch.org/whl/cu128 2>&1 | tail -5 || true \
    && uv pip install "transformers>=4.50.3,<5" "huggingface-hub<1.0" 2>&1 | tail -5 || true

# Build-time smoke test
RUN cd /comfyui && timeout 300 python main.py --quick-test-for-ci --cpu

# Change working directory to ComfyUI
WORKDIR /comfyui

# Support for the network volume — copied BEFORE smoke test? No, after smoke test is fine but
# validate that the yaml loads (including ipadapter/clip_vision keys).
ADD src/extra_model_paths.yaml ./
RUN python -c "import yaml, pathlib; p=pathlib.Path('extra_model_paths.yaml'); cfg=yaml.safe_load(p.read_text()); assert 'runpod_worker_comfy' in cfg, cfg; assert 'ipadapter' in cfg['runpod_worker_comfy'], 'ipadapter missing'; assert 'checkpoints' in cfg['runpod_worker_comfy']; print('extra_model_paths.yaml OK:', list(cfg['runpod_worker_comfy'].keys()))" \
 && python -c "import folder_paths, utils.extra_config; utils.extra_config.load_extra_path_config('extra_model_paths.yaml'); print('extra paths loaded, keys:', [k for k in folder_paths.folder_names_and_paths if any(x in k for x in ('ipadapter','clip_vision','checkpoints','loras'))])"

# Go back to the root
WORKDIR /

# Install Python runtime dependencies for the handler
RUN uv pip install runpod requests websocket-client

# Add application code and scripts
ADD src/start.sh src/network_volume.py handler.py test_input.json ./
RUN chmod +x /start.sh

# Add script to install custom nodes
COPY scripts/comfy-node-install.sh /usr/local/bin/comfy-node-install
RUN chmod +x /usr/local/bin/comfy-node-install

# Prevent pip from asking for confirmation during uninstall steps in custom nodes
ENV PIP_NO_INPUT=1

# Copy helper script to switch Manager network mode at container start
COPY scripts/comfy-manager-set-mode.sh /usr/local/bin/comfy-manager-set-mode
RUN chmod +x /usr/local/bin/comfy-manager-set-mode

# Set the default command to run when starting the container
CMD ["/start.sh"]

# Stage 2: Download models
FROM base AS downloader

ARG HUGGINGFACE_ACCESS_TOKEN
ARG MODEL_TYPE=illustrious

WORKDIR /comfyui

RUN mkdir -p models/checkpoints models/vae models/unet models/clip models/text_encoders models/diffusion_models models/model_patches models/loras models/ipadapter models/clip_vision

RUN if [ "$MODEL_TYPE" = "sdxl" ]; then \
      wget -q -O models/checkpoints/sd_xl_base_1.0.safetensors https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors && \
      wget -q -O models/vae/sdxl_vae.safetensors https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors && \
      wget -q -O models/vae/sdxl-vae-fp16-fix.safetensors https://huggingface.co/madebyollin/sdxl-vae-fp16-fix/resolve/main/sdxl_vae.safetensors; \
    fi

RUN if [ "$MODEL_TYPE" = "sd3" ]; then \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/checkpoints/sd3_medium_incl_clips_t5xxlfp8.safetensors https://huggingface.co/stabilityai/stable-diffusion-3-medium/resolve/main/sd3_medium_incl_clips_t5xxlfp8.safetensors; \
    fi

RUN if [ "$MODEL_TYPE" = "flux1-schnell" ]; then \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/unet/flux1-schnell.safetensors https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/flux1-schnell.safetensors && \
      wget -q -O models/clip/clip_l.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors && \
      wget -q -O models/clip/t5xxl_fp8_e4m3fn.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors && \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/vae/ae.safetensors https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors; \
    fi

RUN if [ "$MODEL_TYPE" = "flux1-dev" ]; then \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/unet/flux1-dev.safetensors https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors && \
      wget -q -O models/clip/clip_l.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors && \
      wget -q -O models/clip/t5xxl_fp8_e4m3fn.safetensors https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors && \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/vae/ae.safetensors https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/ae.safetensors; \
    fi

RUN if [ "$MODEL_TYPE" = "flux1-dev-fp8" ]; then \
      wget -q -O models/checkpoints/flux1-dev-fp8.safetensors https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors; \
    fi

RUN if [ "$MODEL_TYPE" = "z-image-turbo" ]; then \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/text_encoders/qwen_3_4b.safetensors https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors && \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/diffusion_models/z_image_turbo_bf16.safetensors https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors && \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/vae/ae.safetensors https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors && \
      wget -q --header="Authorization: Bearer ${HUGGINGFACE_ACCESS_TOKEN}" -O models/model_patches/Z-Image-Turbo-Fun-Controlnet-Union.safetensors https://huggingface.co/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union/resolve/main/Z-Image-Turbo-Fun-Controlnet-Union.safetensors; \
    fi

# ── illustrious on network volume ──
# When USE_NETWORK_VOLUME=true (default for illustrious), skip bake — models come from /runpod-volume.
ARG USE_NETWORK_VOLUME=true
RUN if [ "$MODEL_TYPE" = "illustrious" ] && [ "$USE_NETWORK_VOLUME" = "true" ]; then \
      echo "FAST: skipping Illustrious bake (USE_NETWORK_VOLUME=true) — checkpoint/Loras live on /runpod-volume"; \
      ls -R models 2>&1 | head -30 || true; \
    elif [ "$MODEL_TYPE" = "illustrious" ]; then \
      wget -q -O models/checkpoints/Illustrious-XL-v2.0.safetensors https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0/resolve/main/Illustrious-XL-v2.0.safetensors && \
      echo "baked Illustrious" && ls -lh models/checkpoints/; \
    fi

# Optional baked turbo LoRA (still tiny; baked even in FAST so /loras is non-empty)
RUN if [ "$MODEL_TYPE" = "illustrious" ] && [ "$USE_NETWORK_VOLUME" != "true" ]; then \
      echo "baking DMD2 LoRA for non-volume image" && \
      wget -q -O models/loras/dmd2-speed-lora-sdxl-pony-illustrious.safetensors https://huggingface.co/Muapi/dmd2-speed-lora-sdxl-pony-illustrious/resolve/main/dmd2-speed-lora-sdxl-pony-illustrious.safetensors 2>&1 | tail -5 || echo "DMD2 fetch failed — non-fatal"; \
    fi

# Stage 3: Final image
FROM base AS final

ARG USE_NETWORK_VOLUME=true
# Only copy models when NOT in network volume mode (FAST: skip to keep image ~7 GB)
COPY --from=downloader /comfyui/models /tmp/downloader_models
RUN if [ "$USE_NETWORK_VOLUME" = "true" ]; then \
      echo "FAST: not copying baked models into final (volume-native) — final has ~empty /comfyui/models"; \
      mkdir -p /comfyui/models; \
    else \
      echo "BAKED: copying models into final"; \
      cp -a /tmp/downloader_models/* /comfyui/models/ 2>&1 | tail -20; \
    fi && rm -rf /tmp/downloader_models && ls -lh /comfyui/models 2>&1 | head -20; du -sh /comfyui/models 2>&1 | head -10
