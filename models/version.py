"""Stable inference-artifact identity, independent of checkout time and evaluation reports."""
import hashlib
from pathlib import Path


def artifact_version(directory):
    directory = Path(directory)
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in {".txt", ".json"} and p.name != "metrics.json") if directory.exists() else []
    if not any(p.suffix == ".txt" for p in files):
        return "none"
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]
