"""Build-state restoration must never turn an archive into arbitrary source-code writes."""
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts import vercel_state
from scripts.vercel_state import restore


class GitBuildTests(unittest.TestCase):
    def archive(self, root, files):
        path = root / "state.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, data in files:
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return path

    def test_runtime_state_is_restored_without_publishing_raw_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.archive(root, [("data/outlook.db", b"test log"), ("data/processed/source.parquet", b"test source")])
            restore(archive, root)
            self.assertEqual((root / "data/outlook.db").read_bytes(), b"test log")
            self.assertFalse((root / "web/public/data").exists())

    def test_archive_cannot_overwrite_code_or_escape_the_checkout(self):
        for name in ["../outside", "/tmp/outside", "data/processed/../../api/main.py", "api/main.py", "web/public/api/places.json"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = self.archive(root, [("data/outlook.db", b"valid first"), (name, b"unsafe")])
                with self.assertRaises(ValueError):
                    restore(archive, root)
                self.assertFalse((root / "data/outlook.db").exists())

    def test_archive_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "state.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                entry = tarfile.TarInfo("data/processed/linked")
                entry.type, entry.linkname = tarfile.SYMTYPE, "../../api"
                archive.addfile(entry)
            with self.assertRaises(ValueError):
                restore(path, root)

    def test_configured_download_failure_does_not_expose_signed_urls_or_fall_back(self):
        url = "https://state.example.invalid/archive.tar.gz?signature=private-build-token"
        with patch.dict("os.environ", {"OUTLOOK_STATE_URL": url}), \
             patch("dotenv.load_dotenv"), \
             patch.object(vercel_state, "urlopen", side_effect=OSError(url)):
            with self.assertRaisesRegex(RuntimeError, "could not be restored") as error:
                vercel_state.main()
            self.assertNotIn("private-build-token", str(error.exception))

    def test_fresh_vercel_build_restores_published_state_without_system_environment_variables(self):
        response = MagicMock()
        response.url = vercel_state.PUBLISHED_STATE_URL
        response.read.side_effect = [b"archive bytes", b""]
        response.__enter__.return_value = response
        with patch.dict("os.environ", {"OUTLOOK_STATE_URL": ""}, clear=True), \
             patch("dotenv.load_dotenv"), \
             patch.object(vercel_state, "urlopen", return_value=response) as download, \
             patch.object(vercel_state, "restore") as restore_state:
            vercel_state.main(published=True)
            self.assertEqual(download.call_args.args[0].full_url, vercel_state.PUBLISHED_STATE_URL)
            restore_state.assert_called_once()

    def test_explicit_archive_takes_precedence_on_vercel(self):
        url = "https://state.example.invalid/custom.tar.gz"
        with patch.dict("os.environ", {"VERCEL": "1", "OUTLOOK_STATE_URL": url}), \
             patch("dotenv.load_dotenv"), \
             patch.object(vercel_state, "urlopen", side_effect=OSError()) as download:
            with self.assertRaises(RuntimeError):
                vercel_state.main(published=True)
            self.assertEqual(download.call_args.args[0].full_url, url)

    def test_owned_published_state_is_preferred_with_only_missing_asset_fallback(self):
        own = "https://github.com/example/outlook-sd/releases/download/state/state.tar.gz"
        for failure in (None, 404, 403, 500):
            with self.subTest(failure=failure):
                response = MagicMock()
                response.url = own if failure is None else vercel_state.PUBLISHED_STATE_URL
                response.read.side_effect = [b"archive", b""]
                response.__enter__.return_value = response
                effects = [response] if failure is None else [HTTPError(own, failure, "unavailable", {}, None), response]
                with patch.dict("os.environ", {"OUTLOOK_STATE_URL": "", "VERCEL_GIT_REPO_OWNER": "example", "VERCEL_GIT_REPO_SLUG": "outlook-sd"}, clear=True), \
                     patch("dotenv.load_dotenv"), patch.object(vercel_state, "urlopen", side_effect=effects) as download, \
                     patch.object(vercel_state, "restore") as restore_state:
                    if failure in {403, 500}:
                        with self.assertRaises(RuntimeError):
                            vercel_state.main(published=True)
                        restore_state.assert_not_called()
                    else:
                        vercel_state.main(published=True)
                        restore_state.assert_called_once()
                    self.assertEqual(download.call_args_list[0].args[0].full_url, own)
                    self.assertEqual(download.call_count, 2 if failure == 404 else 1)

    def test_invalid_repository_metadata_does_not_change_default_archive(self):
        with patch.dict("os.environ", {"VERCEL_GIT_REPO_OWNER": "../elsewhere", "VERCEL_GIT_REPO_SLUG": "outlook-sd"}, clear=True):
            self.assertEqual(vercel_state.published_urls(), [vercel_state.PUBLISHED_STATE_URL])

    def test_local_export_does_not_download_or_replace_runtime_data(self):
        with patch.dict("os.environ", {"VERCEL": "0", "OUTLOOK_STATE_URL": ""}), \
             patch("dotenv.load_dotenv"), \
             patch.object(vercel_state, "urlopen") as download, \
             patch.object(vercel_state, "restore") as restore_state:
            vercel_state.main()
            download.assert_not_called()
            restore_state.assert_not_called()

    def test_archive_size_limits_are_checked_before_restoration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.archive(root, [("data/outlook.db", b"oversized state")])
            with patch.object(vercel_state, "MAX_EXPANDED", 1), self.assertRaises(ValueError):
                restore(archive, root)
            self.assertFalse((root / "data/outlook.db").exists())

    def test_git_configuration_exposes_only_the_existing_static_web_service(self):
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root / "vercel.json").read_text())
        self.assertEqual(set(config["services"]), {"web"})
        self.assertEqual(config["services"]["web"]["root"], "web")
        self.assertEqual(config["services"]["web"]["bindings"], [])
        self.assertNotIn("functions", config)
        self.assertNotIn("builds", config)
        self.assertEqual(config["rewrites"], [{"source": "/(.*)", "destination": {"service": "web"}}])
