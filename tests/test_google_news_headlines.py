from __future__ import annotations

import unittest
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import google_news_headlines


class DefaultsTests(unittest.TestCase):
    def test_uses_dated_output_path(self) -> None:
        self.assertEqual(
            google_news_headlines.default_output_path(date(2026, 9, 10)),
            Path("out/2026-09-10-headlines.csv"),
        )

    def test_builds_a_feed_for_exactly_one_day(self) -> None:
        requested_date = date(2026, 9, 9)
        url = google_news_headlines.dated_feed_url(requested_date)
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.path, "/rss/search")
        self.assertEqual(
            query["q"],
            ["news after:2026-09-09 before:2026-09-10"],
        )

    def test_rejects_future_dates(self) -> None:
        tomorrow = date.today() + timedelta(days=1)
        with self.assertRaisesRegex(Exception, "future"):
            google_news_headlines.parse_news_date(tomorrow.isoformat())

    def test_rejects_dates_in_the_wrong_format(self) -> None:
        with self.assertRaisesRegex(Exception, "YYYY-MM-DD"):
            google_news_headlines.parse_news_date("09/10/2026")


if __name__ == "__main__":
    unittest.main()
