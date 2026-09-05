"""Fetch public GitHub repositories as local directories for ContextForge.

Repositories are downloaded through GitHub's archive endpoint
(``/archive/HEAD.zip``, which resolves the default branch) so no git
installation is required. The extraction is hardened against Zip Slip /
path traversal, and the downloaded copy lives in a temporary directory that
is deleted once the pipeline finishes.
"""

from __future__ import annotations

import io
import re
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib import error as urllib_error
from urllib import request as urllib_request

GITHUB_HOST = "github.com"

# GitHub archive endpoint; the HEAD pseudo-ref resolves the default branch.
# (refs/heads/HEAD.zip is not valid — HEAD is not a branch under refs/heads.)
ARCHIVE_URL_TEMPLATE = "https://github.com/{owner}/{repo}/archive/HEAD.zip"

DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_MEMBERS = 100_000
_DOWNLOAD_CHUNK_SIZE = 64 * 1024

_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class GitHubRepo:
    """A normalized public GitHub repository reference."""

    owner: str
    repo: str

    @property
    def canonical_url(self) -> str:
        """Clean https URL without .git suffix, query parameters, or fragments."""
        return f"https://github.com/{self.owner}/{self.repo}"


class GitHubSourceError(RuntimeError):
    """Base error for GitHub repository fetching failures."""


class GitHubRepoNotFoundError(GitHubSourceError):
    """The repository does not exist or is not publicly accessible."""


class GitHubArchiveError(GitHubSourceError):
    """The archive download or extraction failed a safety check."""


def parse_github_url(url: str) -> GitHubRepo:
    """Parse and normalize a public GitHub repository URL.

    Accepts ``https://github.com/{owner}/{repo}`` (optionally suffixed with
    ``.git``) and strips any query parameters or fragments.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise ValueError("Repository URL is empty.")

    candidate = candidate.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    if candidate.lower().endswith(".git"):
        candidate = candidate[:-4].rstrip("/")

    parts = candidate.split("/")
    if len(parts) != 5:
        raise ValueError("GitHub URL must look like https://github.com/{owner}/{repo}.")
    scheme = parts[0].lower()
    if scheme not in ("https:", "http:"):
        raise ValueError("GitHub repository URL must start with https://")
    if parts[2].lower() != GITHUB_HOST:
        raise ValueError("Only public github.com repository URLs are supported.")

    owner, repo = parts[3], parts[4]
    if not _OWNER_PATTERN.match(owner):
        raise ValueError(f"Invalid GitHub owner name: '{owner}'.")
    if not _REPO_PATTERN.match(repo):
        raise ValueError(f"Invalid GitHub repository name: '{repo}'.")

    return GitHubRepo(owner=owner, repo=repo)


def _fetch_archive(repo: GitHubRepo, *, timeout: float, max_bytes: int) -> bytes:
    """Stream the repository archive into memory, enforcing the size limit."""
    http_request = urllib_request.Request(
        ARCHIVE_URL_TEMPLATE.format(owner=repo.owner, repo=repo.repo),
        headers={"User-Agent": "ContextForge/0.1"},
    )
    try:
        with urllib_request.urlopen(http_request, timeout=timeout) as response:
            buffer = io.BytesIO()
            total = 0
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise GitHubArchiveError(
                        f"GitHub archive for {repo.canonical_url} exceeds the "
                        f"{max_bytes} byte safety limit."
                    )
                buffer.write(chunk)
    except urllib_error.HTTPError as exc:
        if exc.code == 404:
            raise GitHubRepoNotFoundError(
                f"GitHub repository {repo.canonical_url} was not found or is not public."
            ) from exc
        raise GitHubSourceError(
            f"GitHub archive download for {repo.canonical_url} failed with HTTP {exc.code}."
        ) from exc
    except urllib_error.URLError as exc:
        raise GitHubSourceError(
            f"Could not reach GitHub to download {repo.canonical_url}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise GitHubSourceError(
            f"Timed out while downloading the archive for {repo.canonical_url}."
        ) from exc
    return buffer.getvalue()


def _locate_project_root(extraction_dir: Path) -> Path:
    """Return the directory the pipeline should scan.

    GitHub archives wrap the contents in a single top-level folder
    (``{repo}-{ref}/``); unwrap it when present.
    """
    entries = list(extraction_dir.iterdir())
    if not entries:
        raise GitHubArchiveError("GitHub archive is empty.")
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extraction_dir


def _safe_extract(archive: bytes, dest: Path, *, max_uncompressed_bytes: int) -> Path:
    """Extract the archive into ``dest`` with Zip Slip protection.

    Every member must resolve inside ``dest``; symlinks and oversized
    contents are rejected before anything touches the disk.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            if len(members) > DEFAULT_MAX_ARCHIVE_MEMBERS:
                raise GitHubArchiveError(
                    f"GitHub archive contains too many entries "
                    f"(>{DEFAULT_MAX_ARCHIVE_MEMBERS})."
                )
            uncompressed = sum(member.file_size for member in members)
            if uncompressed > max_uncompressed_bytes:
                raise GitHubArchiveError(
                    f"GitHub archive expands to {uncompressed} bytes, over the "
                    f"{max_uncompressed_bytes} byte safety limit."
                )
            dest_root = dest.resolve()
            for member in members:
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise GitHubArchiveError(
                        f"Refusing symlink entry in GitHub archive: {member.filename}"
                    )
                target = (dest / member.filename).resolve()
                if target != dest_root and not target.is_relative_to(dest_root):
                    raise GitHubArchiveError(
                        f"Unsafe path in GitHub archive: {member.filename}"
                    )
            bundle.extractall(dest)
    except zipfile.BadZipFile as exc:
        raise GitHubArchiveError(
            "Downloaded GitHub archive is not a valid zip file."
        ) from exc
    return _locate_project_root(dest)


@contextmanager
def checkout_github_repository(
    repo: GitHubRepo,
    *,
    timeout_seconds: float = DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_extracted_bytes: int = DEFAULT_MAX_EXTRACTED_BYTES,
) -> Iterator[Path]:
    """Download and extract a public GitHub repository into a temp directory.

    The yielded path stays valid for the entire ``with`` block (the full
    ContextForge pipeline); the temporary copy is deleted on exit.
    """
    with tempfile.TemporaryDirectory(prefix="contextforge-github-") as tmp:
        dest = Path(tmp) / "archive"
        dest.mkdir()
        archive = _fetch_archive(
            repo, timeout=timeout_seconds, max_bytes=max_archive_bytes
        )
        yield _safe_extract(archive, dest, max_uncompressed_bytes=max_extracted_bytes)
