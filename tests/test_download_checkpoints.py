import hashlib
import io
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1] / 'scripts/download_checkpoints.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class DownloadTests(unittest.TestCase):
    def test_login_preflight_happens_before_pro_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            response = io.BytesIO(b'')
            response.status = 200
            response.headers = {'Content-Type': 'text/html'}
            response.url = 'https://auth.civitai.com/login'
            manifest = {'schema_version': 1, 'assets': [{'path': 'checkpoints/weight', 'size': 100,
                        'sha256': 'a' * 64, 'url': 'https://civitai.com/api/download/models/1'}]}
            with patch.object(installer, 'urlopen', return_value=response), patch.object(installer, 'remove_pro') as cleanup:
                with self.assertRaisesRegex(RuntimeError, 'CIVITAI_API_TOKEN'):
                    installer.prepare(directory, manifest, remove=True, allow_unmounted=True)
            cleanup.assert_not_called()

    def test_login_html_is_rejected_without_writing_a_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            response = io.BytesIO(b'<html>Login</html>')
            response.status = 200
            response.headers = {'Content-Type': 'text/html'}
            response.url = 'https://auth.civitai.com/login'
            asset = {'size': 100, 'sha256': 'a' * 64}
            with patch.object(installer, 'urlopen', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'CIVITAI_API_TOKEN'):
                    installer.download_file('https://civitai.com/api/download/models/1', path, asset)
            self.assertFalse(path.with_name('weight.part').exists())

    def test_html_partial_is_discarded_before_resuming(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            path.with_name('weight.part').write_bytes(b'<!DOCTYPE html><html>Login</html>')
            response = io.BytesIO(b'good')
            response.status = 200
            response.headers = {}
            asset = {'size': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
            with patch.object(installer, 'urlopen', return_value=response) as get:
                installer.download_file('https://example.invalid', path, asset)
            self.assertIsNone(get.call_args.args[0].get_header('Range'))
            self.assertEqual(path.read_bytes(), b'good')

    def test_cleanup_rejects_symlink_component_before_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pro = root / 'models/qwen-21-pro/diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf'
            pro.parent.mkdir(parents=True)
            pro.write_bytes(b'pro')
            with patch.object(Path, 'is_symlink', autospec=True, side_effect=lambda p: p == pro.parent):
                with self.assertRaisesRegex(RuntimeError, 'symlink'):
                    installer.remove_pro(root, True)
            self.assertEqual(pro.read_bytes(), b'pro')

    def test_cleanup_rejects_symlink_to_turbo_inside_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            turbo = root / 'models/qwen-image-21/turbo.gguf'
            turbo.parent.mkdir(parents=True)
            turbo.write_bytes(b'keep')
            pro = root / 'models/qwen-21-pro/diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf'
            pro.parent.mkdir(parents=True)
            try:
                pro.symlink_to(turbo)
            except OSError:
                self.skipTest('Symlink creation unavailable on this Windows account')
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                installer.remove_pro(root, True)
            self.assertEqual(turbo.read_bytes(), b'keep')

    def test_resume_appends_only_valid_range_and_verifies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            path.with_name('weight.part').write_bytes(b'ab')
            asset = {'size': 6, 'sha256': hashlib.sha256(b'abcdef').hexdigest()}
            response = io.BytesIO(b'cdef')
            response.status = 206
            response.headers = {'Content-Range': 'bytes 2-5/6'}
            with patch.object(installer, 'urlopen', return_value=response) as get:
                installer.download_file('https://example.invalid', path, asset)
            self.assertEqual(get.call_args.args[0].get_header('Range'), 'bytes=2-')
            self.assertEqual(path.read_bytes(), b'abcdef')
            self.assertFalse(path.with_name('weight.part').exists())

    def test_ignored_range_restarts_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            path.with_name('weight.part').write_bytes(b'ab')
            asset = {'size': 6, 'sha256': hashlib.sha256(b'abcdef').hexdigest()}
            response = io.BytesIO(b'abcdef')
            response.status = 200
            response.headers = {}
            with patch.object(installer, 'urlopen', return_value=response):
                installer.download_file('https://example.invalid', path, asset)
            self.assertEqual(path.read_bytes(), b'abcdef')

    def test_bad_checksum_never_promotes_download(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            asset = {'size': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
            response = io.BytesIO(b'evil')
            response.status = 200
            response.headers = {}
            with patch.object(installer, 'urlopen', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'checksum'):
                    installer.download_file('https://example.invalid', path, asset)
            self.assertFalse(path.exists())

    def test_removal_is_opt_in_and_preserves_turbo_and_unknown_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pro = root / 'models/qwen-21-pro/diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf'
            pro.parent.mkdir(parents=True)
            pro.write_bytes(b'pro')
            extra = pro.parent / 'personal.gguf'
            extra.write_bytes(b'keep')
            turbo = root / 'models/qwen-image-21/turbo.gguf'
            turbo.parent.mkdir(parents=True)
            turbo.write_bytes(b'turbo')
            installer.remove_pro(root, False)
            self.assertTrue(pro.exists())
            installer.remove_pro(root, True)
            self.assertFalse(pro.exists())
            self.assertTrue(extra.exists())
            self.assertTrue(turbo.exists())

    def test_corrupt_final_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weight'
            path.write_bytes(b'wrong')
            asset = {'size': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
            with self.assertRaisesRegex(RuntimeError, 'Unverified existing'):
                installer.download_file('https://example.invalid', path, asset)
            self.assertEqual(path.read_bytes(), b'wrong')

    def test_symlink_escape_is_rejected_before_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(installer.Path, 'resolve', return_value=Path('/outside')):
                with self.assertRaisesRegex(RuntimeError, 'escapes'):
                    installer.checked_path(root, 'models/weight')


if __name__ == '__main__':
    unittest.main()
