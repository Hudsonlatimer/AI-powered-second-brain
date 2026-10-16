# Second brain

**Ask a question. The answer has to come from this repo, its commits, or your shell history.**

`brain` indexes one git repository, the latest commits, and this machine's shell history. The index stays under your user profile. Ollama embeds and answers on localhost. Nothing is sent to a hosted model.

```text
uv sync --extra dev
uv run brain ask --demo
```

`--demo` needs no Ollama and no network. It indexes a one-function fixture and prints the excerpts it was allowed to use. The function it should find is [examples/fixture_repo/retry.py](examples/fixture_repo/retry.py):

```python
def retry_after(attempt: int) -> int:
    """The retry helper waits before trying the request again."""
    return attempt * 2
```

Progress goes to stderr. Stdout is the answer and the sources:

```text
The retry helper is retry_after. [F1]

Sources
[C1] ea7ff2f Add the retry helper
Add the retry helper

files: retry.py

[F1] retry.py:1-3
def retry_after(attempt: int) -> int:
    """The retry helper waits before trying the request again."""
    return attempt * 2

[S1] shell line 1
pytest -q
```

The commit hash changes each time `--demo` runs, because the fixture is copied into a temporary git repository.

## Index a repository

The path has to be a git checkout. Existing tests do not have to pass. A dirty worktree is fine, because this tool only reads.

```text
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
uv run brain index C:\path\to\repo
uv run brain ask "where is the retry helper?"
uv run brain status
```

On macOS or Linux, pass a path such as `~/src/repo`. Python 3.11 or newer. Without uv: `python -m venv .venv`, activate it, then `pip install -e ".[dev]"`.

`index` remembers the repo in `.brain/config.json` under your home directory (`%USERPROFILE%` on Windows, `~` on macOS and Linux). Later `ask` and `status` use that repo. The vectors live in `.brain/indexes/` there, not in the repository.

Stdout for `ask` is the answer plus the excerpts. Progress goes to stderr. If Ollama is not running, `index` and `ask` name that on stderr and exit 1.

`status` prints how many file, commit, and shell chunks are stored, and how many shell lines were skipped because they looked like secrets.

## What is stored

- Text files git does not ignore. Python is split with tree-sitter on functions and classes. Other text is split into overlapping 40-line windows. Binaries, files over 1 MB, and lockfiles are skipped.
- The latest 300 commits: hash, date, subject, body, and the paths touched. Diffs are not stored.
- The last 2,000 lines of PowerShell history (`ConsoleHost_history.txt`). `~/.bash_history` and `~/.zsh_history` are included when those files exist. Blank lines, duplicate lines, and lines that look like secrets are dropped. The patterns are `api_key`, `token=`, `password=`, `Bearer`, `AKIA`, and private-key blocks.

Running `index` again hashes each chunk and stores only the new ones.

Each excerpt shown to the model gets an id: `F1` for a file and line range, `C1` for a commit, `S1` for a shell line. The source list is printed even when the model cites nothing. Embeddings use `nomic-embed-text`. Answers use `qwen2.5:7b`. Override them with `OLLAMA_EMBED_MODEL`, `OLLAMA_CHAT_MODEL`, and `OLLAMA_BASE_URL` (default `http://localhost:11434`).

The model is told to say when the excerpts do not contain the answer. That instruction is not a proof that the sentence is fully supported.

## Development

```text
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The default suite uses a deterministic embedder and does not call Ollama. `uv run pytest -m live` sends one embed call to the local server. CI runs Ruff and the default suite on Python 3.12 and 3.14.

## License

[MIT](LICENSE)
