"""Remote project sources for the ContextForge pipeline."""

from .github import (
    ARCHIVE_URL_TEMPLATE,
    DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
    DEFAULT_MAX_ARCHIVE_BYTES,
    DEFAULT_MAX_EXTRACTED_BYTES,
    GitHubArchiveError,
    GitHubRepo,
    GitHubRepoNotFoundError,
    GitHubSourceError,
    checkout_github_repository,
    parse_github_url,
)

__all__ = [
    "ARCHIVE_URL_TEMPLATE",
    "DEFAULT_DOWNLOAD_TIMEOUT_SECONDS",
    "DEFAULT_MAX_ARCHIVE_BYTES",
    "DEFAULT_MAX_EXTRACTED_BYTES",
    "GitHubArchiveError",
    "GitHubRepo",
    "GitHubRepoNotFoundError",
    "GitHubSourceError",
    "checkout_github_repository",
    "parse_github_url",
]
