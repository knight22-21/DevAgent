"""Tests for string_utils — test_title_case fails because the function is missing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.string_utils import count_words, reverse, title_case, truncate


def test_reverse():
    assert reverse("hello") == "olleh"
    assert reverse("") == ""


def test_count_words():
    assert count_words("hello world") == 2
    assert count_words("  one  ") == 1


def test_truncate():
    assert truncate("hello world", 8) == "hello..."
    assert truncate("hi", 10) == "hi"


def test_title_case():
    assert title_case("hello world") == "Hello World"
    assert title_case("the quick brown fox") == "The Quick Brown Fox"
    assert title_case("") == ""
    assert title_case("already Title") == "Already Title"
