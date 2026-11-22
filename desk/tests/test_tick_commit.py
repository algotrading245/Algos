"""The nightly desk commit: gitignored desk paths (kept local) must not fail the commit of the tracked ones."""
import subprocess

from desk import clocks, paths, tick


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)


def test_commit_skips_ignored_paths(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text("desk/board.jsonl\ndesk/journal/*.jsonl\n", encoding="utf-8")
    (tmp_path / "desk" / "journal").mkdir(parents=True)
    (tmp_path / "desk" / "journal" / "2026-10-21.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "desk" / "board.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "desk" / "playbooks").mkdir()
    (tmp_path / "desk" / "playbooks" / "metals.md").write_text("# metals\n", encoding="utf-8")
    monkeypatch.setattr(paths, "ROOT", tmp_path)

    assert tick.commit(clocks.now()) is True  # push fails (no remote): logged, still True
    files = _git(tmp_path, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert files == ["desk/playbooks/metals.md"]
    assert tick.commit(clocks.now()) is True  # nothing new: no empty commit
