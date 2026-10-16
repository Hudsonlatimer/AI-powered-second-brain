"""Typer commands. Answers go to stdout. Progress and failures go to stderr."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from brain.ask import answer_question, index_repository
from brain.demo import DEMO_QUESTION, run_demo
from brain.errors import BrainError
from brain.ollama import OllamaClient
from brain.store import load_meta, load_repo

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command("index")
def index_cmd(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, dir_okay=True)],
) -> None:
    """Index a repository, its commits, and this machine's shell history."""
    index_repository(path, OllamaClient())


@app.command()
def ask(
    question: Annotated[str | None, typer.Argument()] = None,
    demo: Annotated[bool, typer.Option("--demo", help="Run the bundled fixture offline")] = False,
) -> None:
    """Answer a question from the indexed excerpts."""
    if demo:
        print(run_demo(question or DEMO_QUESTION), end="")
        return
    if not question:
        raise BrainError("invalid_input", "Pass a question, or use --demo.")
    print(answer_question(question, OllamaClient(), OllamaClient()), end="")


@app.command()
def status() -> None:
    """Show the last index for the saved repository."""
    repo = load_repo()
    meta = load_meta(repo)
    print(f"repo: {repo}")
    print(f"indexed: {meta['indexed_at']}")
    print(f"files: {meta['files']}")
    print(f"commits: {meta['commits']}")
    print(f"shell: {meta['shell']}")
    print(f"skipped secrets: {meta['skipped_secrets']}")


def main(argv: list[str] | None = None) -> int:
    try:
        app(args=argv, standalone_mode=False)
    except BrainError as exc:
        print(f"{exc.kind}: {exc}", file=sys.stderr)
        return 1
    except typer.Exit as exc:
        return 0 if exc.exit_code is None else exc.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
