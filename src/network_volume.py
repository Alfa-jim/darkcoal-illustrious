"""
Network Volume diagnostics for darkcoal-illustrious (FAST variant).

Mirrors darkcoal-qwen-fast network_volume.py but with Illustrious paths.
Enable diagnostics by setting NETWORK_VOLUME_DEBUG=true.

Volume expected at /runpod-volume (serverless) — Pods may also show it
as /workspace (compat symlink handled in start.sh).
"""

import os

MODEL_TYPES = {
    "checkpoints": [".safetensors", ".ckpt", ".pt", ".pth", ".bin"],
    "clip": [".safetensors", ".pt", ".bin"],
    "clip_vision": [".safetensors", ".pt", ".bin", ".json"],
    "configs": [".yaml", ".json"],
    "controlnet": [".safetensors", ".pt", ".pth", ".bin"],
    "embeddings": [".safetensors", ".pt", ".bin"],
    "loras": [".safetensors", ".pt"],
    "ipadapter": [".safetensors", ".pt", ".bin"],
    "pulid": [".safetensors", ".pt", ".bin"],
    "upscale_models": [".safetensors", ".pt", ".pth"],
    "vae": [".safetensors", ".pt", ".bin"],
    "unet": [".safetensors", ".pt", ".bin"],
    "text_encoders": [".gguf", ".safetensors", ".bin"],
    "diffusion_models": [".gguf", ".safetensors", ".bin"],
}


def is_network_volume_debug_enabled():
    return os.environ.get("NETWORK_VOLUME_DEBUG", "false").lower() == "true"


def run_network_volume_diagnostics():
    print("=" * 70)
    print("NETWORK VOLUME DIAGNOSTICS (NETWORK_VOLUME_DEBUG=true)")
    print("=" * 70)

    extra_model_paths_file = "/comfyui/extra_model_paths.yaml"
    print("\n[1] Checking extra_model_paths.yaml...")
    if os.path.isfile(extra_model_paths_file):
        print(f"    ✓ FOUND: {extra_model_paths_file}")
        with open(extra_model_paths_file, "r") as f:
            for line in f.read().split("\n"):
                print(f"      {line}")
    else:
        print(f"    ✗ NOT FOUND: {extra_model_paths_file}")

    runpod_volume = "/runpod-volume"
    print(f"\n[2] Checking volume mount at {runpod_volume} (and /workspace compat)...")
    for p in ["/runpod-volume", "/workspace"]:
        if os.path.isdir(p):
            print(f"    ✓ exists: {p}")
        else:
            print(f"    - not found: {p}")
    if not os.path.isdir(runpod_volume):
        print("    ✗ NOT MOUNTED — attach Network Volume to endpoint (same region!).")
        print("=" * 70)
        return

    models_dir = os.path.join(runpod_volume, "models")
    print("\n[3] Checking directory structure...")
    if os.path.isdir(models_dir):
        print(f"    ✓ FOUND: {models_dir}")
    else:
        print(f"    ✗ NOT FOUND: {models_dir}")
        print_expected_structure()
        print("=" * 70)
        return

    print("\n[4] Scanning model directories...")
    found_any = False
    for model_type, extensions in MODEL_TYPES.items():
        model_path = os.path.join(models_dir, model_type)
        if os.path.isdir(model_path):
            files = []
            try:
                for f in os.listdir(model_path):
                    fp = os.path.join(model_path, f)
                    if os.path.isfile(fp):
                        ext = os.path.splitext(f)[1].lower()
                        if ext in extensions:
                            size = os.path.getsize(fp)
                            files.append(f"{f} ({format_size(size)})")
                            found_any = True
                        else:
                            files.append(f"{f} (⚠️ ignored - {ext})")
            except Exception as e:
                print(f"    {model_type}/: Error - {e}")
                continue
            if files:
                print(f"\n    {model_type}/:")
                for f in files:
                    print(f"      - {f}")
            else:
                print(f"\n    {model_type}/: (empty)")
        else:
            print(f"\n    {model_type}/: (not found)")

    print("\n[5] Summary")
    if found_any:
        print("    ✓ Models found on network volume.")
    else:
        print("    ⚠️  No valid model files found!")
    print_expected_structure()
    print("=" * 70)


def print_expected_structure():
    print("\n    Expected structure:")
    print("    /runpod-volume/")
    print("    └── models/")
    print("        ├── checkpoints/    <- Illustrious-XL-v2.0.safetensors (6.5 GB)")
    print("        ├── loras/          <- dmd2-speed-lora-sdxl-pony-illustrious.safetensors (~788 MB) + LCM etc")
    print("        ├── vae/            <- (optional; Illustrious is self-contained)")
    print("        ├── ipadapter/      <- ip-adapter_sdxl.safetensors")
    print("        ├── clip_vision/    <- image_encoder model.safetensors + config.json (IPAdapter)")
    print("        ├── controlnet/     <- (optional)")
    print("        └── upscale_models/ <- (optional)")


def format_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
