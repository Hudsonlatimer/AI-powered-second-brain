"""LanceDB index under the user profile, outside the target repo."""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import lancedb

from brain.collect import Chunk
from brain.errors import BrainError

_TABLE = "chunks"


def brain_home() -> Path:
    override = os.environ.get("BRAIN_HOME", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".brain"


def index_dir(repo: Path) -> Path:
    key = os.path.normcase(str(repo.resolve()))
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return brain_home() / "indexes" / digest


def save_repo(repo: Path) -> None:
    path = brain_home() / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"repo": str(repo.resolve())}) + "\n", encoding="utf-8")


def load_repo() -> Path:
    path = brain_home() / "config.json"
    if not path.is_file():
        raise BrainError("missing_index", "Run brain index PATH first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    repo = Path(data["repo"])
    if _open_table(index_dir(repo)) is None:
        raise BrainError("missing_index", "Run brain index PATH first.")
    return repo


def existing_hashes(repo: Path) -> set[str]:
    table = _open_table(index_dir(repo))
    if table is None:
        return set()
    column = table.to_arrow().column("content_hash")
    return {str(item) for item in column.to_pylist()}


def add_chunks(repo: Path, chunks: list[Chunk], vectors: list[list[float]]) -> int:
    if not chunks:
        return 0
    rows = [
        {
            "vector": vector,
            "text": chunk.text,
            "kind": chunk.kind,
            "ref": chunk.ref,
            "start": chunk.start,
            "end": chunk.end,
            "content_hash": chunk.content_hash,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    directory = index_dir(repo)
    directory.mkdir(parents=True, exist_ok=True)
    database = lancedb.connect(str(directory / "lancedb"))
    names = _table_names(database)
    if _TABLE not in names:
        database.create_table(_TABLE, data=rows)
    else:
        database.open_table(_TABLE).add(rows)
    return len(rows)


def search_vectors(repo: Path, vector: list[float], limit: int = 8) -> list[dict]:
    table = _open_table(index_dir(repo))
    if table is None:
        raise BrainError("missing_index", "Run brain index PATH first.")
    rows = table.search(vector).limit(limit).to_list()
    hits: list[dict] = []
    for row in rows:
        hits.append(
            {
                "text": str(row["text"]),
                "kind": str(row["kind"]),
                "ref": str(row["ref"]),
                "start": int(row["start"]),
                "end": int(row["end"]),
            }
        )
    return hits


def save_meta(repo: Path, *, skipped_secrets: int) -> dict:
    counts = _counts(repo)
    payload = {
        "indexed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": counts.get("file", 0),
        "commits": counts.get("commit", 0),
        "shell": counts.get("shell", 0),
        "skipped_secrets": skipped_secrets,
    }
    path = index_dir(repo) / "meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return payload


def load_meta(repo: Path) -> dict:
    path = index_dir(repo) / "meta.json"
    if not path.is_file():
        raise BrainError("missing_index", "Run brain index PATH first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _counts(repo: Path) -> dict[str, int]:
    table = _open_table(index_dir(repo))
    if table is None:
        return {}
    counts: dict[str, int] = {}
    for kind in table.to_arrow().column("kind").to_pylist():
        name = str(kind)
        counts[name] = counts.get(name, 0) + 1
    return counts


def _open_table(directory: Path):
    database_path = directory / "lancedb"
    if not database_path.exists():
        return None
    database = lancedb.connect(str(database_path))
    if _TABLE not in _table_names(database):
        return None
    return database.open_table(_TABLE)


def _table_names(database) -> set[str]:
    listed = database.list_tables()
    return set(listed.tables)
