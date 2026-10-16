"""Failures the CLI can name without a stack trace."""


class BrainError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)
