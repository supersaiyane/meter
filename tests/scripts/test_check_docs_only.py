"""The shortcut gate for documents alone, and the refusal that keeps it honest.

The refusal is the half that matters: a code file anywhere in the change, committed, staged,
unstaged or untracked, must send the change to `make verify`. The git half runs against a
throwaway repository, because what it decides comes from what git reports.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Loaded by path, as the other script tests load theirs: `scripts` is not a package.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_docs_only.py"
spec = importlib.util.spec_from_file_location("check_docs_only", SCRIPT)
assert spec and spec.loader
check_docs_only = importlib.util.module_from_spec(spec)
sys.modules["check_docs_only"] = check_docs_only
spec.loader.exec_module(check_docs_only)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with one commit on main, and a branch off it to change."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.local")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "README.md").write_text("start\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "start")
    git(tmp_path, "switch", "-q", "-c", "work")
    return tmp_path


class TestWhatIsADocument:
    @pytest.mark.parametrize(
        "path",
        [
            "INDEX.md",
            "next-in-scope.txt",
            "docs/registry.yaml",
            "docs/architecture/file-graph.json",
            "tasks/STATUS.md",
            "finops-web/README.md",
        ],
    )
    def test_documents(self, path: str) -> None:
        assert check_docs_only.is_document(path)

    @pytest.mark.parametrize(
        "path",
        [
            "Makefile",
            "finops_api/main.py",
            "finops-web/src/App.tsx",
            "migrations/versions/0029_x.py",
            ".env.example",
            "pyproject.toml",
            "infra/terraform/hub/main.tf",
        ],
    )
    def test_not_documents(self, path: str) -> None:
        assert not check_docs_only.is_document(path)

    def test_the_refused_are_named_once_and_in_order(self) -> None:
        assert check_docs_only.not_documents(["b.py", "a.md", "Makefile", "b.py"]) == [
            "Makefile",
            "b.py",
        ]


class TestWhatChanged:
    def test_a_committed_document_alone_passes(self, repo: Path) -> None:
        (repo / "README.md").write_text("changed\n")
        git(repo, "commit", "-qam", "docs")
        changed = check_docs_only.changed_paths("main", cwd=repo)
        assert changed == {"README.md"}
        assert check_docs_only.not_documents(changed) == []

    def test_committed_staged_unstaged_and_untracked_code_are_all_seen(self, repo: Path) -> None:
        (repo / "committed.py").write_text("a = 1\n")
        git(repo, "add", "committed.py")
        git(repo, "commit", "-qm", "code")
        (repo / "staged.py").write_text("b = 1\n")
        git(repo, "add", "staged.py")
        (repo / "app.py").write_text("x = 2\n")
        (repo / "untracked.py").write_text("c = 1\n")
        changed = check_docs_only.changed_paths("main", cwd=repo)
        assert check_docs_only.not_documents(changed) == [
            "app.py",
            "committed.py",
            "staged.py",
            "untracked.py",
        ]

    def test_a_deleted_code_file_is_a_code_change(self, repo: Path) -> None:
        git(repo, "rm", "-q", "app.py")
        git(repo, "commit", "-qm", "remove")
        assert check_docs_only.not_documents(check_docs_only.changed_paths("main", cwd=repo)) == [
            "app.py"
        ]

    def test_a_link_to_shared_tooling_is_not_a_change(
        self, repo: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        tooling = tmp_path_factory.mktemp("venv")
        (repo / ".venv").symlink_to(tooling, target_is_directory=True)
        assert check_docs_only.changed_paths("main", cwd=repo) == set()

    def test_a_base_git_cannot_find_fails_loudly(self, repo: Path) -> None:
        with pytest.raises(check_docs_only.GitError, match="nowhere"):
            check_docs_only.changed_paths("nowhere", cwd=repo)
