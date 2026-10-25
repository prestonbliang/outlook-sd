"""Restore build-time state. Never run a pipeline or modify a remote service."""
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
# Release assets are not included in Git checkouts or copied when a repository is forked.
# Hosted builds share the project's published forecast snapshot unless explicitly overridden.
PUBLISHED_STATE_URL = "https://github.com/raunavm/outlook-sd/releases/download/state/state.tar.gz"
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_EXPANDED = 4 * MAX_DOWNLOAD


def restore(archive, root=ROOT):
    """Allow only ordinary runtime files; reject traversal/links before writing anything."""
    root = Path(root)
    with tarfile.open(archive, "r:gz") as state:
        members = state.getmembers()
        if len(members) > 10000 or sum(m.size for m in members) > MAX_EXPANDED:
            raise ValueError("State archive exceeds the build limits")
        for member in members:
            path = PurePosixPath(member.name)
            allowed = path == PurePosixPath("data/outlook.db") or path.is_relative_to("data/processed")
            if member.isdir() and path == PurePosixPath("data"):
                allowed = True
            if not allowed or path.is_absolute() or ".." in path.parts or "\\" in member.name or not (member.isfile() or member.isdir()):
                raise ValueError("State archive contains a path or file type outside the runtime data directories")
            if not (root / path).resolve().is_relative_to(root.resolve()):
                raise ValueError("State archive destination escapes the checkout")
        # Stage all reads first so a corrupt download cannot partially replace existing inputs.
        with tempfile.TemporaryDirectory(prefix="outlook-state-") as directory:
            staging = Path(directory)
            for member in members:
                if member.isfile():
                    target = staging / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with state.extractfile(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
            for member in members:
                if member.isfile():
                    target = root / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(staging / member.name, target)


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    url = os.environ.get("OUTLOOK_STATE_URL", "").strip()
    if not url and os.environ.get("VERCEL") == "1":
        url = PUBLISHED_STATE_URL
        print("Restoring the project's published forecast snapshot for this Vercel build.")
    if not url:
        print("No state URL configured; using local runtime data if present, otherwise explicit unavailable forecasts.")
        return
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("OUTLOOK_STATE_URL must be an HTTPS archive URL without embedded credentials")
    try:
        with tempfile.TemporaryDirectory(prefix="outlook-download-") as directory:
            archive = Path(directory) / "state.tar.gz"
            with urlopen(Request(url, headers={"User-Agent": "OutlookSD-Vercel-build"}), timeout=60) as response, archive.open("wb") as output:
                if urlparse(response.url).scheme != "https":
                    raise ValueError("State download must remain on HTTPS")
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise ValueError("State archive exceeds the download limit")
                    output.write(chunk)
            restore(archive)
    except Exception:  # noqa: BLE001 -- every download/parser error must redact signed URLs
        # Signed URLs may carry credentials. Never echo the URL or urllib's original exception.
        raise RuntimeError("Runtime state could not be restored. Check archive access, format and build limits.") from None
    print("Runtime state restored for static API export.")


if __name__ == "__main__":
    main()
