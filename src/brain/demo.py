"""Offline embedder and answer used by --demo."""

import hashlib
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from brain.ask import answer_question, index_repository

FIXTURE = Path(__file__).resolve().parents[2] / "examples" / "fixture_repo"
DEMO_QUESTION = "where is the retry helper?"
_DIM = 64


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(text) for text in texts]


class ScriptedChat:
    def chat(self, _system: str, human: str) -> str:
        for block in re.split(r"\n(?=\[)", human):
            if "retry_after" not in block:
                continue
            match = re.search(r"\[([FCS]\d+)\]", block)
            if match:
                return f"The retry helper is retry_after. [{match.group(1)}]"
        return "The excerpts do not contain the answer."


def run_demo(question: str = DEMO_QUESTION) -> str:
    previous_home = os.environ.get("BRAIN_HOME")
    previous_history = os.environ.get("BRAIN_HISTORY_FILES")
    try:
        with tempfile.TemporaryDirectory(prefix="second-brain-") as tmp:
            root = Path(tmp)
            os.environ["BRAIN_HOME"] = str(root / "home")
            repo = root / "fixture"
            shutil.copytree(FIXTURE, repo)
            history = root / "history.txt"
            history.write_text("pytest -q\n", encoding="utf-8")
            os.environ["BRAIN_HISTORY_FILES"] = str(history)
            _seed_git(repo)
            index_repository(repo, FakeEmbedder())
            return answer_question(question, FakeEmbedder(), ScriptedChat())
    finally:
        _restore("BRAIN_HOME", previous_home)
        _restore("BRAIN_HISTORY_FILES", previous_history)


def _vector(text: str) -> list[float]:
    values = [0.0] * _DIM
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        values[int.from_bytes(digest[:4], "little") % _DIM] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _seed_git(repo: Path) -> None:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "second-brain"
    env["GIT_AUTHOR_EMAIL"] = "second-brain@example.com"
    env["GIT_COMMITTER_NAME"] = "second-brain"
    env["GIT_COMMITTER_EMAIL"] = "second-brain@example.com"
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-m", "Add the retry helper"],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _restore(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous
