import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.security import redact
from pipeline.storage import atomic_output


class StorageTests(unittest.TestCase):
    def test_failed_write_preserves_previous_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "table.parquet"
            target.write_bytes(b"original")
            with self.assertRaises(RuntimeError):
                with atomic_output(target) as temporary:
                    temporary.write_bytes(b"partial")
                    raise RuntimeError("interrupted")
            self.assertEqual(target.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_successful_write_replaces_in_same_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested/table.parquet"
            with atomic_output(target) as temporary:
                self.assertEqual(temporary.parent, target.parent)
                temporary.write_bytes(b"complete")
            self.assertEqual(target.read_bytes(), b"complete")
            self.assertFalse(temporary.exists())

    def test_encoded_operational_keys_are_redacted(self):
        with patch.dict(os.environ, {"AIRNOW_API_KEY": "private+/ key"}):
            for value in ["private+/ key", "private%2B%2F%20key", "private%2B%2F+key"]:
                self.assertNotIn(value, redact(f"request failed: {value}"))
        self.assertEqual(redact("https://test.invalid/?API_KEY=unknown&site=1"), "https://test.invalid/?API_KEY=***&site=1")


if __name__ == "__main__":
    unittest.main()
