import os
import subprocess
from pathlib import Path

import pytest

from brain.chunk import chunk_text
from brain.cli import main
from brain.collect import collect_files, filter_history
from brain.demo import FakeEmbedder
from brain.store import search_vectors


def test_python_chunks_keep_function_lines():
    source = "def add(left, right):\n    return left + right\n\ndef retry_after(attempt):\n    return attempt\n"
    chunks = chunk_text("retry.py", source)
    retry = [item for item in chunks if "retry_after" in item[2]]
    assert retry
    assert retry[0][0] == 4


def test_line_windows_overlap():
    text = "\n".join(f"line {number}" for number in range(1, 51))
    windows = chunk_text("notes.md", text)
    assert windows[0][0] == 1
    assert windows[0][1] == 40
    assert windows[1][0] == 33


def test_gitignore_skips_ignored_files(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_commit(
        repo,
        {
            "secret.txt": "hidden\n",
            "keep.py": "def keep():\n    return 1\n",
            ".gitignore": "secret.txt\n",
        },
    )
    refs = [chunk.ref for chunk in collect_files(repo)]
    assert "keep.py" in refs
    assert "secret.txt" not in refs


def test_secret_lines_are_dropped():
    lines = [
        "pytest -q",
        "export API_KEY=abc",
        "token=sekret",
        "password = hunter2",
        "Bearer abc.def",
        "AKIAIOSFODNN7EXAMPLE",
        "-----BEGIN RSA PRIVATE KEY-----",
        ": 1710000000:0;pytest -q",
    ]
    kept, skipped = filter_history(lines)
    assert kept == ["pytest -q"]
    assert skipped == 6


def test_search_ranks_the_matching_chunk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("BRAIN_HISTORY_FILES", "")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_commit(
        repo,
        {
            "retry.py": 'def retry_after(attempt):\n    """The retry helper waits."""\n    return attempt\n',
            "other.py": "def other():\n    return 0\n",
        },
    )
    from brain.ask import index_repository

    first = index_repository(repo, FakeEmbedder())
    assert first["added"] > 0
    second = index_repository(repo, FakeEmbedder())
    assert second["added"] == 0
    hits = search_vectors(repo.resolve(), FakeEmbedder().embed(["where is the retry helper?"])[0])
    assert hits[0]["kind"] == "file"
    assert "retry_after" in hits[0]["text"]


def test_demo_cites_the_fixture(capsys: pytest.CaptureFixture[str]):
    code = main(["ask", "--demo"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "retry_after" in captured.out
    assert "[F1]" in captured.out


def test_missing_question_is_an_error(capsys: pytest.CaptureFixture[str]):
    assert main(["ask"]) == 1
    assert "invalid_input" in capsys.readouterr().err


@pytest.mark.live
def test_live_ollama_embeds():
    from brain.ollama import OllamaClient

    vectors = OllamaClient().embed(["retry helper"])
    assert len(vectors) == 1
    assert len(vectors[0]) > 8


def _git_commit(repo: Path, files: dict[str, str]) -> None:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "second-brain"
    env["GIT_AUTHOR_EMAIL"] = "second-brain@example.com"
    env["GIT_COMMITTER_NAME"] = "second-brain"
    env["GIT_COMMITTER_EMAIL"] = "second-brain@example.com"
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, env=env)
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True, env=env
    )
