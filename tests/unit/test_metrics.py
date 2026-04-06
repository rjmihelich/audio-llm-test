"""Tests for evaluation metrics."""

import pytest

from backend.app.evaluation.metrics import word_error_rate, character_error_rate


class TestWER:
    def test_perfect_match(self):
        assert word_error_rate("hello world", "hello world") == 0.0

    def test_case_insensitive(self):
        assert word_error_rate("Hello World", "hello world") == 0.0

    def test_one_substitution(self):
        # "the cat sat" vs "the dog sat" — 1 sub / 3 words
        wer = word_error_rate("the cat sat", "the dog sat")
        assert wer == pytest.approx(1 / 3)

    def test_one_insertion(self):
        # "the cat" vs "the big cat" — 1 ins / 2 words
        wer = word_error_rate("the cat", "the big cat")
        assert wer == pytest.approx(0.5)

    def test_one_deletion(self):
        # "the big cat" vs "the cat" — 1 del / 3 words
        wer = word_error_rate("the big cat", "the cat")
        assert wer == pytest.approx(1 / 3)

    def test_empty_reference(self):
        assert word_error_rate("", "") == 0.0
        assert word_error_rate("", "hello") == 1.0

    def test_completely_wrong(self):
        wer = word_error_rate("navigate to home", "play some music")
        assert wer == pytest.approx(1.0)

    def test_punctuation_ignored(self):
        assert word_error_rate("Hello, world!", "hello world") == 0.0


class TestCER:
    def test_perfect_match(self):
        assert character_error_rate("hello", "hello") == 0.0

    def test_one_error(self):
        cer = character_error_rate("hello", "hallo")
        assert cer == pytest.approx(1 / 5)

    def test_empty(self):
        assert character_error_rate("", "") == 0.0
        assert character_error_rate("", "a") == 1.0
