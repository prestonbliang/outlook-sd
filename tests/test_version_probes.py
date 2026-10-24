import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from models.version import artifact_version
from pipeline.probes.run_all import main as probe_all


class VersionAndProbeTests(unittest.TestCase):
    def test_version_tracks_model_inputs_not_checkout_or_metric_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.txt"
            model.write_text("model weights")
            (root / "thresholds.json").write_text('{"high":0.5}')
            first = artifact_version(root)
            model.touch()
            (root / "metrics.json").write_text('{"mae":1}')
            self.assertEqual(first, artifact_version(root))
            (root / "thresholds.json").write_text('{"high":0.7}')
            self.assertNotEqual(first, artifact_version(root))

    def test_missing_model_has_no_version(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(artifact_version(directory), "none")

    def test_probe_failure_returns_nonzero_and_continues(self):
        modules = [SimpleNamespace(name="probe_a"), SimpleNamespace(name="probe_b")]
        with patch("pipeline.probes.run_all.pkgutil.iter_modules", return_value=modules), \
             patch("pipeline.probes.run_all.importlib.import_module", side_effect=[RuntimeError("failed"), None]) as imported, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe_all(), 1)
            self.assertEqual(imported.call_count, 2)

    def test_successful_probes_return_zero(self):
        with patch("pipeline.probes.run_all.pkgutil.iter_modules", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe_all(), 0)


if __name__ == "__main__":
    unittest.main()
