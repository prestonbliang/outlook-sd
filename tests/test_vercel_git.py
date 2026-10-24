"""Build-state restoration must never turn an archive into arbitrary source-code writes."""
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

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
        self.assertNotIn("functions", config)
        self.assertNotIn("builds", config)
        self.assertEqual(config["rewrites"], [{"source": "/(.*)", "destination": {"service": "web"}}])
