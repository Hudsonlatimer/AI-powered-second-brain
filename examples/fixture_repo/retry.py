def retry_after(attempt: int) -> int:
    """The retry helper waits before trying the request again."""
    return attempt * 2
