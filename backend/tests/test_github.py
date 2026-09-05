"""Tests for public GitHub repository support in ContextForge.

All network access is mocked — no test in this suite touches the real GitHub
endpoint, per the project requirement that network-dependent tests stay out of
the mandatory suite.
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib import error as urllib_error

from fastapi import HTTPException
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes import analyze_project, optimize_context
from app.api.schemas import ContextOptimizeRequest, ProjectAnalyzeRequest
from app.remote import (
    GitHubArchiveError,
    GitHubRepo,
    GitHubRepoNotFoundError,
    GitHubSourceError,
    checkout_github_repository,
    parse_github_url,
)


def _zip_payload(entries: dict[str, bytes]) -> bytes:
    """Build an in-memory zip archive with the given member name -> content."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o644 << 16
            bundle.writestr(info, data)
    return buffer.getvalue()


def _fake_urlopen(payload: bytes):
    """Build a urlopen replacement serving ``payload`` from memory."""
    response = MagicMock()
    response.status = 200
    response.read.side_effect = [payload, b""]
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False

    def _urlopen(request, timeout=None):  # noqa: ANN001, ANN202
        return context

    return _urlopen


SAMPLE_REPO_ZIP = _zip_payload(
    {
        "flask-example-main/app.py": (
            b"from flask import Flask\n"
            b"app = Flask(__name__)\n"
            b"\n"
            b"@app.route('/')\n"
            b"def index():\n"
            b"    return 'Hello'\n"
        ),
        "flask-example-main/README.md": b"# flask-example\n",
    }
)


class ParseGitHubUrlTests(unittest.TestCase):
    def test_valid_url(self) -> None:
        repo = parse_github_url("https://github.com/tsungtwu/flask-example")
        self.assertEqual(repo, GitHubRepo(owner="tsungtwu", repo="flask-example"))
        self.assertEqual(repo.canonical_url, "https://github.com/tsungtwu/flask-example")

    def test_git_suffix_is_stripped(self) -> None:
        repo = parse_github_url("https://github.com/tsungtwu/flask-example.git")
        self.assertEqual(repo, GitHubRepo(owner="tsungtwu", repo="flask-example"))

    def test_query_and_fragment_are_stripped(self) -> None:
        repo = parse_github_url(
            "https://github.com/tsungtwu/flask-example?abc=123&x=y#readme"
        )
        self.assertEqual(repo, GitHubRepo(owner="tsungtwu", repo="flask-example"))
        self.assertEqual(repo.canonical_url, "https://github.com/tsungtwu/flask-example")

    def test_trailing_slash_and_whitespace(self) -> None:
        repo = parse_github_url("  https://github.com/owner/repo/  \n")
        self.assertEqual(repo, GitHubRepo(owner="owner", repo="repo"))

    def test_invalid_urls_raise_value_error(self) -> None:
        invalid = [
            "",
            "   ",
            "https://gitlab.com/owner/repo",
            "https://github.com/only-owner",
            "https://github.com/owner/repo/tree/main",
            "https://github.com/owner/",
            "github.com/owner/repo",
            "ftp://github.com/owner/repo",
            "https://github.com/-badowner/repo",
            "https://github.com/owner/bad repo",
        ]
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_github_url(url)


class CheckoutGitHubRepositoryTests(unittest.TestCase):
    def test_safe_extraction_and_unwrap(self) -> None:
        with patch(
            "app.remote.github.urllib_request.urlopen",
            new=_fake_urlopen(SAMPLE_REPO_ZIP),
        ):
            with checkout_github_repository(
                GitHubRepo(owner="tsungtwu", repo="flask-example")
            ) as root:
                self.assertEqual(root.name, "flask-example-main")
                self.assertTrue((root / "app.py").is_file())
                self.assertTrue((root / "README.md").is_file())

    def test_temp_directory_is_deleted_after_checkout(self) -> None:
        created = []
        real_temporary_directory = tempfile.TemporaryDirectory

        def spy_temporary_directory(*args, **kwargs):
            handle = real_temporary_directory(*args, **kwargs)
            created.append(Path(handle.name))
            return handle

        with patch(
            "app.remote.github.urllib_request.urlopen",
            new=_fake_urlopen(SAMPLE_REPO_ZIP),
        ), patch(
            "app.remote.github.tempfile.TemporaryDirectory",
            side_effect=spy_temporary_directory,
        ):
            with checkout_github_repository(
                GitHubRepo(owner="tsungtwu", repo="flask-example")
            ) as root:
                temp_root = root.parents[1]  # root -> archive -> <TemporaryDirectory>
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())
        self.assertFalse(temp_root.exists())

    def test_zip_slip_traversal_is_rejected(self) -> None:
        payload = _zip_payload(
            {"flask-example-main/app.py": b"print('ok')\n", "../evil.txt": b"pwned"}
        )
        with patch(
            "app.remote.github.urllib_request.urlopen", new=_fake_urlopen(payload)
        ):
            with self.assertRaises(GitHubArchiveError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="evil")
                ):
                    pass

    def test_absolute_member_path_is_rejected(self) -> None:
        payload = _zip_payload({"/abs/evil.txt": b"pwned"})
        with patch(
            "app.remote.github.urllib_request.urlopen", new=_fake_urlopen(payload)
        ):
            with self.assertRaises(GitHubArchiveError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="evil")
                ):
                    pass

    def test_symlink_member_is_rejected(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            info = zipfile.ZipInfo("flask-example-main/link")
            info.external_attr = 0o120777 << 16  # S_IFLNK | permissions
            bundle.writestr(info, "/etc/passwd")
        with patch(
            "app.remote.github.urllib_request.urlopen",
            new=_fake_urlopen(buffer.getvalue()),
        ):
            with self.assertRaises(GitHubArchiveError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="evil")
                ):
                    pass

    def test_archive_size_limit_is_enforced(self) -> None:
        payload = _zip_payload(
            {"flask-example-main/big.bin": b"x" * (64 * 1024)}
        )
        with patch(
            "app.remote.github.urllib_request.urlopen", new=_fake_urlopen(payload)
        ):
            with self.assertRaises(GitHubArchiveError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="big"),
                    max_extracted_bytes=1024,
                ):
                    pass

    def test_missing_repo_maps_to_not_found(self) -> None:
        def _urlopen(request, timeout=None):
            raise urllib_error.HTTPError(
                "https://github.com/owner/missing", 404, "Not Found", None, io.BytesIO(b"")
            )

        with patch("app.remote.github.urllib_request.urlopen", new=_urlopen):
            with self.assertRaises(GitHubRepoNotFoundError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="missing")
                ):
                    pass

    def test_network_failure_maps_to_source_error(self) -> None:
        def _urlopen(request, timeout=None):
            raise urllib_error.URLError("name resolution failed")

        with patch("app.remote.github.urllib_request.urlopen", new=_urlopen):
            with self.assertRaises(GitHubSourceError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="repo")
                ):
                    pass

    def test_corrupt_zip_maps_to_archive_error(self) -> None:
        with patch(
            "app.remote.github.urllib_request.urlopen", new=_fake_urlopen(b"not a zip")
        ):
            with self.assertRaises(GitHubArchiveError):
                with checkout_github_repository(
                    GitHubRepo(owner="owner", repo="repo")
                ):
                    pass


class EndpointGitHubSupportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "auth.py").write_text(
            "def google_oauth_login():\n    '''Google OAuth login flow helper.'''\n"
            "    return 'oauth login token'\n",
            encoding="utf-8",
        )
        (self.root / "notes.txt").write_text("random notes\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_local_project_path_still_works(self) -> None:
        response = analyze_project(
            ProjectAnalyzeRequest(project_path=str(self.root))
        )
        self.assertEqual(response.project_path, str(self.root.resolve()))
        # notes.txt is noise-filtered by the existing pipeline; only auth.py remains.
        self.assertEqual(
            [item.path for item in response.files], ["auth.py"]
        )
        self.assertEqual(response.summary.analyzed_files_count, 1)

    def test_missing_local_path_still_returns_404(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            analyze_project(
                ProjectAnalyzeRequest(project_path="Z:/definitely/not/here")
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_invalid_github_url_returns_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            analyze_project(
                ProjectAnalyzeRequest(
                    repository_url="https://gitlab.com/owner/repo"
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_analyze_with_repository_url(self) -> None:
        with patch(
            "app.remote.github.urllib_request.urlopen",
            new=_fake_urlopen(SAMPLE_REPO_ZIP),
        ):
            response = analyze_project(
                ProjectAnalyzeRequest(
                    repository_url="https://github.com/tsungtwu/flask-example?abc=123"
                )
            )
        self.assertEqual(
            response.project_path, "https://github.com/tsungtwu/flask-example"
        )
        paths = [item.path for item in response.files]
        self.assertIn("app.py", paths)

    def test_optimize_with_repository_url(self) -> None:
        payload = _zip_payload(
            {
                "demo-main/oauth.py": (
                    b"def google_oauth_login(user):\n"
                    b"    '''Google OAuth login flow.'''\n"
                    b"    token = exchange_code(user)\n"
                    b"    return token\n"
                ),
                "demo-main/README.md": b"# demo\n",
            }
        )
        created = []
        real_temporary_directory = tempfile.TemporaryDirectory

        def spy_temporary_directory(*args, **kwargs):
            handle = real_temporary_directory(*args, **kwargs)
            created.append(Path(handle.name))
            return handle

        with patch(
            "app.remote.github.urllib_request.urlopen", new=_fake_urlopen(payload)
        ), patch(
            "app.remote.github.tempfile.TemporaryDirectory",
            side_effect=spy_temporary_directory,
        ):
            response = optimize_context(
                ContextOptimizeRequest(
                    repository_url="https://github.com/owner/demo.git",
                    query="Why is google oauth login failing?",
                    token_budget=2000,
                )
            )

        self.assertEqual(
            response.project_path, "https://github.com/owner/demo"
        )
        self.assertGreaterEqual(response.total_selected, 1)
        self.assertGreater(len(response.optimized_context), 0)
        self.assertGreater(response.metrics.original_tokens, 0)
        selected_paths = [item.path for item in response.selected_files]
        self.assertIn("oauth.py", selected_paths)
        # The temporary clone must be gone once the pipeline completed.
        self.assertTrue(all(not path.exists() for path in created))

    def test_repository_url_takes_precedence_over_project_path(self) -> None:
        with patch(
            "app.remote.github.urllib_request.urlopen",
            new=_fake_urlopen(SAMPLE_REPO_ZIP),
        ):
            response = analyze_project(
                ProjectAnalyzeRequest(
                    project_path=str(self.root),
                    repository_url="https://github.com/tsungtwu/flask-example",
                )
            )
        self.assertEqual(
            response.project_path, "https://github.com/tsungtwu/flask-example"
        )


class RequestValidationTests(unittest.TestCase):
    def test_missing_source_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectAnalyzeRequest()
        with self.assertRaises(ValidationError):
            ContextOptimizeRequest(query="why?")

    def test_blank_source_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectAnalyzeRequest(project_path="   ")
        with self.assertRaises(ValidationError):
            ContextOptimizeRequest(query="why?", repository_url="  ")

    def test_repository_url_alone_is_accepted(self) -> None:
        request = ContextOptimizeRequest(
            repository_url="https://github.com/owner/repo", query="why?"
        )
        self.assertEqual(request.repository_url, "https://github.com/owner/repo")
        self.assertIsNone(request.project_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
