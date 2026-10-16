"""Retrieve excerpts and answer from those excerpts only."""

import sys

from brain.collect import collect_commits, collect_files, collect_shell, ensure_repo
from brain.ollama import embed_batched
from brain.store import add_chunks, existing_hashes, load_repo, save_meta, save_repo, search_vectors

SYSTEM = (
    "Answer using only the excerpts. Cite excerpt ids in square brackets, such as [F1]. "
    "If the excerpts do not contain the answer, say so."
)


def index_repository(repo, embedder) -> dict:
    root = repo.resolve()
    ensure_repo(root)
    print("Indexing files", file=sys.stderr)
    files = collect_files(root)
    print("Indexing commits", file=sys.stderr)
    commits = collect_commits(root)
    print("Indexing shell history", file=sys.stderr)
    shell, skipped = collect_shell()
    chunks = files + commits + shell
    known = existing_hashes(root)
    fresh = [chunk for chunk in chunks if chunk.content_hash not in known]
    if fresh:
        vectors = embed_batched(embedder, [chunk.text for chunk in fresh])
        add_chunks(root, fresh, vectors)
    save_repo(root)
    meta = save_meta(root, skipped_secrets=skipped)
    print(
        f"Stored {len(fresh)} new chunks ({len(chunks) - len(fresh)} already stored).",
        file=sys.stderr,
    )
    return {"added": len(fresh), "skipped_secrets": skipped, "meta": meta, "chunks": len(chunks)}


def answer_question(question: str, embedder, chatter) -> str:
    repo = load_repo()
    vector = embedder.embed([question])[0]
    hits = assign_ids(search_vectors(repo, vector))
    if not hits:
        return "The excerpts do not contain the answer.\n"
    reply = chatter.chat(SYSTEM, build_prompt(question, hits))
    return render_answer(reply, hits)


def assign_ids(rows: list[dict]) -> list[dict]:
    counts = {"file": 0, "commit": 0, "shell": 0}
    prefix = {"file": "F", "commit": "C", "shell": "S"}
    labeled: list[dict] = []
    for row in rows:
        kind = row["kind"]
        counts[kind] = counts.get(kind, 0) + 1
        item = dict(row)
        item["id"] = f"{prefix.get(kind, 'X')}{counts[kind]}"
        item["label"] = _label(row)
        labeled.append(item)
    return labeled


def build_prompt(question: str, hits: list[dict]) -> str:
    lines = [f"Question: {question}", "", "Excerpts:"]
    for hit in hits:
        lines.append(f"[{hit['id']}] {hit['label']}")
        lines.append(hit["text"])
        lines.append("")
    return "\n".join(lines)


def render_answer(answer: str, hits: list[dict]) -> str:
    lines = [answer.strip(), "", "Sources"]
    for hit in hits:
        lines.append(f"[{hit['id']}] {hit['label']}")
        lines.append(hit["text"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _label(row: dict) -> str:
    if row["kind"] == "file":
        return f"{row['ref']}:{row['start']}-{row['end']}"
    if row["kind"] == "commit":
        subject = row["text"].splitlines()[0]
        return f"{row['ref'][:7]} {subject}"
    return f"shell line {row['start']}"
