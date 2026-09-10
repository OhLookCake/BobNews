from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import google_news_headlines


class DefaultsTests(unittest.TestCase):
    def test_uses_dated_output_path(self) -> None:
        self.assertEqual(
            google_news_headlines.default_output_path(date(2026, 9, 10)),
            Path("out/2026-09-10-headlines.csv"),
        )


if __name__ == "__main__":
    unittest.main()
