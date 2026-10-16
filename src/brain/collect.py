"""Read files, commits, and shell history into chunks."""

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from brain.chunk import chunk_text
from brain.errors import BrainError

_TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".rst",
    ".sh",
    ".ps1",
    ".css",
    ".html",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".rs",
    ".go",
    ".java",
    ".rb",
    ".ini",
    ".cfg",
}
_BARE_NAMES = {"readme", "license", "makefile", "dockerfile"}
_LOCK_NAMES = {
    "uv.lock",
    "package-lock.json",
    "poetry.lock",
    "cargo.lock",
    "pnpm-lock.yaml",
    "yarn.lock",
}
_SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
_MAX_BYTES = 1_048_576
_COMMIT_LIMIT = 300
_HISTORY_LIMIT = 2000
_SECRET = re.compile(
    r"(api[_-]?key|token\s*=|password\s*[=:]|bearer\s+\S|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Chunk:
    kind: str
    ref: str
    start: int
    end: int
    text: str

    @property
    def content_hash(self) -> str:
        payload = f"{self.kind}\0{self.ref}\0{self.start}\0{self.end}\0{self.text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_repo(repo: Path) -> None:
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise BrainError("not_git", f"{repo} is not a git repository.")


def collect_files(repo: Path) -> list[Chunk]:
    candidates = _text_files(repo)
    ignored = _ignored(repo, [item[0] for item in candidates])
    chunks: list[Chunk] = []
    for relative, path in candidates:
        if relative in ignored:
            continue
        text = _read_text(path)
        if text is None:
            continue
        for start, end, snippet in chunk_text(relative, text):
            chunks.append(Chunk("file", relative, start, end, snippet))
    return chunks


def collect_commits(repo: Path, limit: int = _COMMIT_LIMIT) -> list[Chunk]:
    log = _git(
        repo,
        "log",
        f"-n{limit}",
        "--pretty=format:%H%x1f%aI%x1f%s%x1f%b%x1e",
    )
    if log.returncode != 0:
        return []
    names = _git(repo, "log", f"-n{limit}", "--name-only", "--pretty=format:%H")
    files_by_hash = _parse_name_only(names.stdout)
    chunks: list[Chunk] = []
    for record in log.stdout.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) < 3:
            continue
        sha, _date, subject = parts[0].strip(), parts[1].strip(), parts[2].strip()
        body = parts[3].strip()[:2000] if len(parts) > 3 else ""
        touched = files_by_hash.get(sha, [])
        text = subject
        if body:
            text = f"{text}\n\n{body}"
        if touched:
            text = f"{text}\n\nfiles: {', '.join(touched)}"
        if text.strip():
            chunks.append(Chunk("commit", sha, 0, 0, text.strip()))
    return chunks


def history_files() -> list[Path]:
    if "BRAIN_HISTORY_FILES" in os.environ:
        raw = os.environ["BRAIN_HISTORY_FILES"]
        if not raw.strip():
            return []
        return [Path(part) for part in raw.split(os.pathsep) if part]
    found: list[Path] = []
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        found.append(
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "PowerShell"
            / "PSReadLine"
            / "ConsoleHost_history.txt"
        )
    home = Path.home()
    found.append(home / ".bash_history")
    found.append(home / ".zsh_history")
    return [path for path in found if path.is_file()]


def collect_shell(paths: list[Path] | None = None) -> tuple[list[Chunk], int]:
    chosen = history_files() if paths is None else paths
    chunks: list[Chunk] = []
    skipped = 0
    seen: set[str] = set()
    for path in chosen:
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-_HISTORY_LIMIT:]
        origin = len(lines) - len(tail)
        for offset, raw in enumerate(tail):
            line = normalize_history_line(raw)
            if not line:
                continue
            if is_secret(line):
                skipped += 1
                continue
            if line in seen:
                continue
            seen.add(line)
            line_no = origin + offset + 1
            chunks.append(Chunk("shell", path.name, line_no, line_no, line))
    return chunks, skipped


def filter_history(lines: list[str]) -> tuple[list[str], int]:
    kept: list[str] = []
    skipped = 0
    seen: set[str] = set()
    for raw in lines:
        line = normalize_history_line(raw)
        if not line:
            continue
        if is_secret(line):
            skipped += 1
            continue
        if line in seen:
            continue
        seen.add(line)
        kept.append(line)
    return kept, skipped


def normalize_history_line(raw: str) -> str:
    line = raw.strip()
    if line.startswith(":") and ";" in line:
        line = line.split(";", 1)[1].strip()
    return line


def is_secret(line: str) -> bool:
    return _SECRET.search(line) is not None


def _text_files(repo: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if name.lower() in _LOCK_NAMES:
                continue
            if not _is_text_name(name):
                continue
            try:
                if path.stat().st_size > _MAX_BYTES:
                    continue
            except OSError:
                continue
            relative = path.relative_to(repo).as_posix()
            found.append((relative, path))
    return found


def _is_text_name(name: str) -> bool:
    suffix = Path(name).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return True
    return name.lower() in _BARE_NAMES


def _read_text(path: Path) -> str | None:
    try:
        sample = path.read_bytes()[:1024]
    except OSError:
        return None
    if b"\0" in sample:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _ignored(repo: Path, relative: list[str]) -> set[str]:
    if not relative:
        return set()
    payload = "\0".join(relative) + "\0"
    completed = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"],
        cwd=repo,
        input=payload.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    text = completed.stdout.decode("utf-8", errors="replace")
    return {part for part in text.split("\0") if part}


def _parse_name_only(stdout: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    current = ""
    files: list[str] = []

    def flush() -> None:
        if current:
            found[current] = list(files)

    for line in stdout.splitlines():
        stripped = line.strip()
        if len(stripped) == 40 and all(char in "0123456789abcdef" for char in stripped):
            flush()
            current = stripped
            files = []
        elif stripped and current:
            files.append(stripped)
    flush()
    return found


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
