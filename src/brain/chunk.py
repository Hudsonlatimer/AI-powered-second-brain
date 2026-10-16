"""Split source into function chunks or overlapping line windows."""

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

_PARSER = Parser(Language(tspython.language()))
_SYMBOLS = {"function_definition", "class_definition"}
_WINDOW = 40
_OVERLAP = 8


def chunk_text(path: str, text: str) -> list[tuple[int, int, str]]:
    if path.endswith(".py"):
        symbols = python_symbols(text)
        if symbols:
            return symbols
    return line_windows(text)


def python_symbols(source: str) -> list[tuple[int, int, str]]:
    tree = _PARSER.parse(source.encode("utf-8"))
    lines = source.splitlines()
    found: list[tuple[int, int, str]] = []

    def walk(node) -> None:
        if node.type in _SYMBOLS:
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            snippet = "\n".join(lines[start - 1 : end]).strip()
            if snippet:
                found.append((start, end, snippet))
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return found


def line_windows(
    text: str, size: int = _WINDOW, overlap: int = _OVERLAP
) -> list[tuple[int, int, str]]:
    lines = text.splitlines()
    if not lines:
        return []
    step = max(1, size - overlap)
    windows: list[tuple[int, int, str]] = []
    start = 0
    while start < len(lines):
        end = min(len(lines), start + size)
        snippet = "\n".join(lines[start:end]).strip()
        if snippet:
            windows.append((start + 1, end, snippet))
        if end == len(lines):
            break
        start += step
    return windows
