#!/usr/bin/env python3
"""Generate the standalone CPU-Pod download bootstrap."""
import argparse
import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def make_command():
    source = (ROOT / 'scripts/download_checkpoints.py').read_text().encode()
    lock = (ROOT / 'model-lock.json').read_text().encode()
    return f'''#!/usr/bin/env bash
set -euo pipefail
# Requires Python 3.11+ and an attached network volume. Stop Pro workers first
# if using REMOVE_QWEN_PRO=1. Otherwise no Pro weights are removed.
python3 - <<'ILLUSTRIOUS_BOOTSTRAP'
import base64, hashlib, json, os, pathlib, sys
if sys.version_info < (3, 11):
    raise SystemExit('Python 3.11+ required; use a current Ubuntu CPU Pod.')
source = base64.b64decode('{base64.b64encode(source).decode()}')
lock = base64.b64decode('{base64.b64encode(lock).decode()}')
assert hashlib.sha256(source).hexdigest() == '{hashlib.sha256(source).hexdigest()}'
assert hashlib.sha256(lock).hexdigest() == '{hashlib.sha256(lock).hexdigest()}'
namespace = {{'__name__': 'illustrious_installer'}}
exec(compile(source, 'download_checkpoints.py', 'exec'), namespace)
namespace['prepare'](os.environ.get('MODEL_VOLUME_ROOT', '/workspace'), json.loads(lock), os.environ.get('REMOVE_QWEN_PRO') == '1')
ILLUSTRIOUS_BOOTSTRAP
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = ROOT / 'DOWNLOAD_ON_CPU_POD.sh'
    script = make_command()
    if args.check:
        assert target.read_text() == script, 'Regenerate DOWNLOAD_ON_CPU_POD.sh'
        print('Bootstrap matches installer and model lock')
    else:
        target.write_text(script, newline='\n')
