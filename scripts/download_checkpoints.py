#!/usr/bin/env python3
"""Standalone, dependency-free installer for an already attached network volume."""

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import threading
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def asset_url(asset):
    url = asset['url']
    token = os.environ.get('CIVITAI_API_TOKEN', '')
    if token and url.startswith('https://civitai.com/api/download/'):
        url += '&token=' + quote(token, safe='')
    return url


def verified(path, asset):
    if not path.is_file() or path.stat().st_size != asset['size']:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == asset['sha256']


def download_file(url, destination, asset):
    destination = Path(destination)
    stop = threading.Event()
    started = time.monotonic()
    def report():
        while not stop.wait(1):
            path = destination if destination.exists() else destination.with_name(destination.name + '.part')
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            print(f'  {destination.name}: {size:,}/{asset["size"]:,} bytes '
                  f'({size / asset["size"]:.1%}), {time.monotonic() - started:.0f}s elapsed (download / verification)', flush=True)
    thread = threading.Thread(target=report, daemon=True)
    thread.start()
    try:
        return _download_file(url, destination, asset)
    finally:
        stop.set()
        thread.join()


def _download_file(url, destination, asset):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if verified(destination, asset):
            print(f'Already verified: {destination.name}', flush=True)
            return
        raise RuntimeError(f'Unverified existing file: {destination}. Move it aside before retrying; '
                           'the installer will not overwrite existing model files.')
    partial = destination.with_name(destination.name + '.part')
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == asset['size']:
            break
        if offset > asset['size']:
            raise RuntimeError(f'Partial file larger than expected: {partial}; move it aside')
        headers = {'User-Agent': 'Mozilla/5.0'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        try:
            with urlopen(Request(url, headers=headers), timeout=60) as response:
                if response.status == 206:
                    expected = f'bytes {offset}-{asset["size"] - 1}/{asset["size"]}'
                    if response.headers.get('Content-Range') != expected:
                        raise RuntimeError('Invalid HTTP range response; refusing to append mismatched bytes')
                    mode = 'ab'
                elif response.status == 200:
                    mode = 'wb'  # A server may ignore Range; never append a full response.
                    offset = 0
                else:
                    raise RuntimeError(f'Unexpected download status {response.status}')
                print(f'Downloading {destination.name} ({offset}/{asset["size"]} bytes)', flush=True)
                with partial.open(mode) as output:
                    downloaded, last_report = offset, time.monotonic()
                    while chunk := response.read(8 * 1024 * 1024):
                        downloaded += len(chunk)
                        if downloaded > asset['size']:
                            raise RuntimeError('Download exceeds the pinned file size')
                        output.write(chunk)
                        if time.monotonic() - last_report >= 1:
                            print(f'  {destination.name}: {downloaded / asset["size"]:.0%}', flush=True)
                            last_report = time.monotonic()
                    output.flush()
                    os.fsync(output.fileno())
            if partial.stat().st_size == asset['size']:
                break
        except (URLError, OSError) as exc:
            if attempt == 2:
                raise RuntimeError(f'Download interrupted; rerun to resume {partial}. Check network or Civitai token.') from None
            print('Download interrupted; retrying (URL omitted to protect credentials)', flush=True)
        if attempt < 2:
            time.sleep(2**attempt)
    if not partial.exists() or partial.stat().st_size < asset['size']:
        raise RuntimeError(f'Download incomplete; rerun to resume {partial}')
    print(f'Verifying SHA256: {destination.name} (reading all bytes)...', flush=True)
    if not verified(partial, asset):
        # This file was created exclusively by this installer; a corrupt partial
        # cannot be resumed safely. Preserve existing finalized files above.
        partial.unlink(missing_ok=True)
        raise RuntimeError(f'Size/checksum verification failed for {destination.name}; rerun to download again')
    os.replace(partial, destination)
    print(f'SHA256 verified: {destination.name}', flush=True)


@contextlib.contextmanager
def download_lock(path):
    """OS-released advisory lock, including when an interrupted process dies."""
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.tell() == 0:
                stream.write(b'\0')
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('Another model download is already running on this volume') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError('Another model download is already running on this volume') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def checked_path(volume_root, relative):
    root = Path(volume_root).absolute()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise RuntimeError('Model path escapes the attached volume')
    return target


def remove_pro(volume_root, enabled):
    paths = [checked_path(volume_root, 'models/qwen-21-pro/' + name) for name in (
        'diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf',
        'text_encoders/qwen3vl_8b_int8_convrot.safetensors',
        'vae/qwen_image_2.1_vae_bf16.safetensors', 'model-manifest.json')]
    paths += [path.with_name(path.name + '.part') for path in paths]
    existing = [path for path in paths if path.is_file()]
    print('Pro removal inventory:', flush=True)
    for path in existing:
        print(f'  {path}: {path.stat().st_size:,} bytes', flush=True)
    if not enabled:
        print('Pro retained. Use --remove-pro only after stopping Pro workers.', flush=True)
        return
    for path in existing:
        path.unlink()
        print(f'Removed: {path}', flush=True)


def prepare(volume_root, manifest, remove=False, allow_unmounted=False):
    volume_root = Path(volume_root).absolute()
    if not volume_root.is_dir() or (not allow_unmounted and not os.path.ismount(volume_root)):
        raise RuntimeError(f'{volume_root} is not an attached network-volume mount')
    if manifest.get('schema_version') != 1:
        raise RuntimeError('Unsupported model manifest')
    # Validate ALL destinations before any deletion or download.
    for asset in manifest['assets']:
        checked_path(volume_root, 'models/' + asset['path'])
        if not re.fullmatch(r'[0-9a-f]{64}', asset['sha256']) or asset['size'] <= 0:
            raise RuntimeError('Invalid model checksum/size')
        if asset['path'].split('/')[0] not in ('checkpoints', 'loras', 'ipadapter', 'clip_vision'):
            raise RuntimeError('Unsupported model directory')
    root = checked_path(volume_root, 'models')
    root.mkdir(exist_ok=True)
    with download_lock(root / '.illustrious-install.lock'):
        remove_pro(volume_root, remove)
        for asset in manifest['assets']:
            download_file(asset_url(asset), checked_path(volume_root, 'models/' + asset['path']), asset)
        staging = root / 'illustrious-manifest.json.part'
        staging.write_text(json.dumps(manifest, indent=2) + '\n')
        os.replace(staging, root / 'illustrious-manifest.json')
    print(f'All {len(manifest["assets"])} assets verified. Total: '
          f'{sum(a["size"] for a in manifest["assets"]):,} bytes.', flush=True)
    print('Serverless sees these files under /runpod-volume/models/', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--volume-root', default=os.environ.get('MODEL_VOLUME_ROOT', '/workspace'))
    parser.add_argument('--manifest', type=Path, default=Path(__file__).resolve().parents[1] / 'model-lock.json')
    parser.add_argument('--remove-pro', action='store_true', help='Delete ONLY known Pro assets; stop Pro workers first')
    args = parser.parse_args()
    try:
        prepare(args.volume_root, json.loads(args.manifest.read_text()), args.remove_pro)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')


if __name__ == '__main__':
    main()
