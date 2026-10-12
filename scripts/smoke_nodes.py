"""Check actual ComfyUI node registration via a private CPU server, no weights."""
import json
import subprocess
import sys
import time
from urllib.request import urlopen

process = subprocess.Popen([sys.executable, 'main.py', '--cpu', '--listen', '127.0.0.1', '--port', '18188', '--disable-auto-launch'])
try:
    deadline = time.monotonic() + 180
    info = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('ComfyUI exited before node registration')
        try:
            with urlopen('http://127.0.0.1:18188/object_info', timeout=3) as response:
                info = json.load(response)
            break
        except OSError:
            time.sleep(1)
    if info is None:
        raise RuntimeError('ComfyUI registration timeout')
    for name in ('CheckpointLoaderSimple', 'LoraLoader', 'KSampler', 'IPAdapterModelLoader', 'IPAdapterAdvanced', 'CLIPVisionLoader'):
        assert name in info, f'Missing node: {name}'
    required = info['IPAdapterAdvanced']['input']['required']
    assert required['weight_type'][0].count('linear') == 1
    assert 'V only' in required['embeds_scaling'][0]
    sampler = info['KSampler']['input']['required']
    assert 'euler' in sampler['sampler_name'][0] and 'normal' in sampler['scheduler'][0]
    print('CPU smoke passed: checkpoint, LoRA, sampler and reference nodes registered', flush=True)
finally:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
