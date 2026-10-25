"""Restore build-time state. Never run a pipeline or modify a remote service."""
import argparse
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
# Release assets are not included in Git checkouts or copied when a repository is forked.
# Prefer a deploying fork's own state, retaining the shared snapshot for forks without a release.
PUBLISHED_STATE_URL = "https://github.com/raunavm/outlook-sd/releases/download/state/state.tar.gz"
MAX_DOWNLOAD = 1024 * 1024 * 1024
MAX_EXPANDED = 4 * MAX_DOWNLOAD


def published_urls():
    owner = os.environ.get("VERCEL_GIT_REPO_OWNER", "")
    repo = os.environ.get("VERCEL_GIT_REPO_SLUG", "")
    urls = []
    if all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in {".", ".."} for part in (owner, repo)):
        urls.append(f"https://github.com/{owner}/{repo}/releases/download/state/state.tar.gz")
    if PUBLISHED_STATE_URL not in urls:
        urls.append(PUBLISHED_STATE_URL)
    return urls


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


def main(*, published=False):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    explicit = os.environ.get("OUTLOOK_STATE_URL", "").strip()
    urls = [explicit] if explicit else published_urls() if published else []
    if not explicit and published:
        print("Restoring the project's published forecast snapshot for this Vercel build.")
    if not urls:
        print("No state URL configured; using local runtime data if present, otherwise explicit unavailable forecasts.")
        return
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("OUTLOOK_STATE_URL must be an HTTPS archive URL without embedded credentials")
    try:
        with tempfile.TemporaryDirectory(prefix="outlook-download-") as directory:
            archive = Path(directory) / "state.tar.gz"
            for index, url in enumerate(urls):
                try:
                    response = urlopen(Request(url, headers={"User-Agent": "OutlookSD-Vercel-build"}), timeout=60)
                    break
                except HTTPError as error:
                    if error.code != 404 or index == len(urls) - 1:
                        raise
                    print("No repository-owned state asset; using the shared project snapshot.")
            with response, archive.open("wb") as output:
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--published", action="store_true", help="Default to the project's public forecast snapshot")
    main(published=parser.parse_args().published)
