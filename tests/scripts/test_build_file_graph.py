"""The file graph describes the repository, and its check fails when it does not.

Three defects, found on 2026-10-05, share one shape: a check that passed because it
had examined nothing.

`walk` judged `SKIP_DIRS` against every part of the absolute path, so a checkout
under a directory named tmp, build, dist, scratch or security held no files at all,
and `make doc-sync` wrote an empty graph. `--check` rebuilt the graph and never
compared it with the committed one, so the empty graph passed. And the files came
from the disk rather than from git, so the committed graph held whatever the last
person to run it had lying in their checkout: the declaration files `tsc --build`
writes into `finops-web/dist-types`, which git ignores.

Every case here was watched failing, against the code before the fix or against
the fix with the one line the case guards taken out.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Two modules and the edge between them: the least a graph can hold and still
#: show whether an edge was found.
TWO_MODULES = {
    "finops_core/__init__.py": "",
    "finops_core/a.py": "import finops_core.b\n",
    "finops_core/b.py": "",
}
EDGE = ("finops_core/a.py", "finops_core/b.py", "python")
NOTHING_TO_GRAPH = {"README.md": "nothing here is a graph node\n"}
OUTPUTS = ("file-graph.md", "file-graph.json")

Graph = tuple[list[tuple[str, str, str]], list[str], list[str]]


def load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_file_graph", ROOT / "scripts" / "docs" / "build_file_graph.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Read from the builder at collection, so every name it skips is tried as the
#: name of a directory a checkout lives under. A list written out here would stop
#: covering the next name added to SKIP_DIRS.
SKIPPED_NAMES = sorted(load_builder().SKIP_DIRS)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def checkout(root: Path, files: dict[str, str]) -> Path:
    """A git repository with `files` committed.

    Committed, because most of a repository is tracked files, and a listing that
    saw only untracked ones would pass every case built on a tree nobody had
    committed. The identity and the switches are set here so that nothing in this
    machine's own git configuration, a signing key or a hook, reaches the test.
    """
    root.mkdir(parents=True)
    git(root, "init", "-q")
    write(root, files)
    git(root, "add", "-A")
    git(
        root,
        "-c",
        "user.name=meter",
        "-c",
        "user.email=meter@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "--no-verify",
        "-m",
        "fixture",
    )
    return root


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def graph(builder: ModuleType, monkeypatch: pytest.MonkeyPatch, root: Path) -> Graph:
    monkeypatch.setattr(builder, "ROOT", root)
    built: Graph = builder.build()
    return built


def run(builder: ModuleType, monkeypatch: pytest.MonkeyPatch, root: Path, *argv: str) -> int:
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "OUT_DIR", root / "docs" / "architecture")
    monkeypatch.setattr(sys, "argv", ["build_file_graph.py", *argv])
    return int(builder.main())


# --- which files are in the graph ---------------------------------------------


@pytest.mark.parametrize("name", SKIPPED_NAMES)
def test_a_checkout_under_a_directory_with_a_skipped_name_is_graphed_in_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """A skip is about a directory inside the repository, never about where the
    repository happens to be. Judged on the absolute path, a worktree under
    /private/tmp had no files, and the graph doc-sync wrote there was empty."""
    builder = load_builder()
    root = checkout(tmp_path / name / "meter", TWO_MODULES)

    edges, nodes, _ = graph(builder, monkeypatch, root)

    assert nodes == sorted(TWO_MODULES)
    assert edges == [EDGE]


def test_a_skipped_directory_inside_the_checkout_is_still_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fix moves where a skip is judged, and must not stop skips working."""
    builder = load_builder()
    strays = {f"{name}/stray.py": "" for name in SKIPPED_NAMES if name != ".git"}
    root = checkout(tmp_path / "meter", {**TWO_MODULES, **strays})

    _, nodes, _ = graph(builder, monkeypatch, root)

    assert nodes == sorted(TWO_MODULES)


def test_a_file_git_ignores_is_not_in_the_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The committed graph held declaration files from finops-web/dist-types,
    which `tsc --build` writes and git ignores. So the graph depended on who had
    last built the web bundle, and a strict check would fail for everybody else."""
    builder = load_builder()
    ignored = {".gitignore": "dist-types\n", "dist-types/src/App.d.ts": "export {};\n"}
    root = checkout(tmp_path / "meter", {**TWO_MODULES, **ignored})

    _, nodes, _ = graph(builder, monkeypatch, root)

    assert nodes == sorted(TWO_MODULES)


def test_a_new_file_is_in_the_graph_before_anybody_runs_git_add(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Graphing only tracked files would leave a new file out until it was
    staged, and the graph committed beside it would then be stale."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", TWO_MODULES)
    write(root, {"finops_core/c.py": "import finops_core.a\n"})

    edges, nodes, _ = graph(builder, monkeypatch, root)

    assert "finops_core/c.py" in nodes
    assert ("finops_core/c.py", "finops_core/a.py", "python") in edges


def test_a_file_deleted_but_still_in_the_index_is_not_in_the_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """git lists it until the deletion is staged, and there is nothing to read."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", {**TWO_MODULES, "finops_core/gone.py": ""})
    (root / "finops_core" / "gone.py").unlink()

    _, nodes, _ = graph(builder, monkeypatch, root)

    assert nodes == sorted(TWO_MODULES)


# --- the check ------------------------------------------------------------------


def test_the_check_passes_when_the_committed_graph_is_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of every failing case below, which a check that always
    failed would satisfy."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", TWO_MODULES)

    assert run(builder, monkeypatch, root) == 0
    assert run(builder, monkeypatch, root, "--check") == 0


def test_the_outputs_survive_the_end_of_file_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.pre-commit-config.yaml` runs end-of-file-fixer, which ends every file with
    exactly one newline. An output written any other way would be changed by the
    hook on commit, refused by the check, and changed back by `make graph`: a loop
    nobody could get out of."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", TWO_MODULES)
    assert run(builder, monkeypatch, root) == 0
    for name in OUTPUTS:
        path = root / "docs" / "architecture" / name
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n", encoding="utf-8")

    assert run(builder, monkeypatch, root, "--check") == 0


def test_the_check_fails_when_the_committed_graph_is_stale_and_names_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Naming the file is what makes the failure fixable. A stray untracked file
    is graphed too, and only its name tells the reader it is the cause."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", TWO_MODULES)
    assert run(builder, monkeypatch, root) == 0
    write(root, {"finops_core/c.py": "import finops_core.a\n"})
    capsys.readouterr()

    assert run(builder, monkeypatch, root, "--check") == 1
    out = capsys.readouterr().out
    assert "out of step" in out
    assert "finops_core/c.py" in out


@pytest.mark.parametrize("name", OUTPUTS)
def test_either_output_alone_being_stale_fails_the_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    """Both outputs are compared, so neither can drift while the other is current."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", TWO_MODULES)
    assert run(builder, monkeypatch, root) == 0
    path = root / "docs" / "architecture" / name
    path.write_text(path.read_text(encoding="utf-8") + "drift\n", encoding="utf-8")
    capsys.readouterr()

    assert run(builder, monkeypatch, root, "--check") == 1
    assert f"out of step with the source: {name}." in capsys.readouterr().out


def test_the_check_fails_when_no_graph_was_ever_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = load_builder()
    root = checkout(tmp_path / "meter", TWO_MODULES)

    assert run(builder, monkeypatch, root, "--check") == 1
    assert "out of step" in capsys.readouterr().out


def test_an_empty_graph_fails_the_check_even_when_it_matches_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """What happened on 2026-10-05. doc-sync wrote an empty graph, and a fresh
    build of the same nothing agreed with it, so comparing alone is not enough.
    The outputs are rendered by the builder itself, so they match exactly."""
    builder = load_builder()
    root = checkout(tmp_path / "meter", NOTHING_TO_GRAPH)
    rendered = builder.render([], [])
    write(root, {f"docs/architecture/{name}": text for name, text in rendered.items()})

    assert run(builder, monkeypatch, root, "--check") == 1
    assert "no files" in capsys.readouterr().out


def test_finding_no_files_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = load_builder()
    root = checkout(tmp_path / "meter", NOTHING_TO_GRAPH)

    assert run(builder, monkeypatch, root) == 1
    assert "no files" in capsys.readouterr().out
    assert not (root / "docs").exists()


def test_a_tree_git_does_not_know_is_refused_rather_than_read_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Falling back to the disk would bring back a graph that depends on which
    machine wrote it. The ceiling stops git finding a repository above tmp_path.
    The message is matched on its own words, because tmp_path's name holds the
    word git and would satisfy a looser match."""
    builder = load_builder()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    root = tmp_path / "meter"
    write(root, TWO_MODULES)

    assert run(builder, monkeypatch, root) == 1
    out = capsys.readouterr().out
    assert "could not list the files" in out
    assert "no files found" not in out
    assert not (root / "docs").exists()
