"""String utilities — title_case() is missing and needs to be implemented."""


def reverse(s: str) -> str:
    return s[::-1]


def count_words(s: str) -> int:
    return len(s.split())


def truncate(s: str, max_len: int, suffix: str = "...") -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - len(suffix)] + suffix


# title_case(s: str) -> str is missing here.
# It should convert "hello world" → "Hello World".
# The tests in tests/test_string.py import and call it.
