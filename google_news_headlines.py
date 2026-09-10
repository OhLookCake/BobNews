#!/usr/bin/env python3
"""Save the top Google News headlines and links to a CSV file."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path


DEFAULT_FEED_URL = "https://news.google.com/rss?hl=en-GB&gl=GB&ceid=GB:en"
GLOBAL_FEED_URL = (
    "https://news.google.com/rss/headlines/section/topic/WORLD"
    "?hl=en-GB&gl=GB&ceid=GB:en"
)
SEARCH_FEED_URL = "https://news.google.com/rss/search"


def default_output_path(fetch_date: date | None = None) -> Path:
    """Return the dated default path for a headline fetch."""
    fetched_on = fetch_date or date.today()
    return Path("out") / f"{fetched_on.isoformat()}-headlines.csv"


DEFAULT_OUTPUT = default_output_path()
USER_AGENT = "Mozilla/5.0 (compatible; GoogleNewsHeadlineFetcher/1.0)"
DECODE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je"


def parse_news_date(value: str) -> date:
    """Parse a non-future ISO date for historical headline searches."""
    try:
        news_date = date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from error
    if news_date > date.today():
        raise argparse.ArgumentTypeError("date cannot be in the future")
    return news_date


def dated_feed_url(news_date: date) -> str:
    """Build a Google News RSS search URL constrained to one calendar day."""
    next_date = news_date + timedelta(days=1)
    query = (
        f"news after:{news_date.isoformat()} before:{next_date.isoformat()}"
    )
    parameters = urllib.parse.urlencode(
        {
            "q": query,
            "hl": "en-GB",
            "gl": "GB",
            "ceid": "GB:en",
        }
    )
    return f"{SEARCH_FEED_URL}?{parameters}"


class ArticleDataParser(HTMLParser):
    """Extract Google News article decoding parameters from an HTML page."""

    def __init__(self, article_id: str) -> None:
        super().__init__()
        self.article_id = article_id
        self.timestamp: int | None = None
        self.signature: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if attributes.get("data-n-a-id") != self.article_id:
            return

        timestamp = attributes.get("data-n-a-ts")
        signature = attributes.get("data-n-a-sg")
        if timestamp and signature:
            self.timestamp = int(timestamp)
            self.signature = signature


def get_article_token(google_url: str) -> str:
    """Extract the encoded article ID from a Google News URL."""
    parsed_url = urllib.parse.urlparse(google_url)
    if parsed_url.hostname != "news.google.com":
        raise ValueError(f"Not a Google News URL: {google_url}")

    token = parsed_url.path.rstrip("/").rsplit("/", 1)[-1]
    if not token:
        raise ValueError(f"Missing article ID in Google News URL: {google_url}")
    return token


def get_decoding_parameters(google_url: str) -> tuple[str, int, str]:
    """Get the token, timestamp, and signature needed to resolve an article."""
    token = get_article_token(google_url)
    request = urllib.request.Request(google_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        page = response.read().decode("utf-8", errors="replace")

    parser = ArticleDataParser(token)
    parser.feed(page)
    if parser.timestamp is None or parser.signature is None:
        raise ValueError("Google News did not provide article decoding parameters")
    return token, parser.timestamp, parser.signature


def resolve_publisher_links(
    headlines: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Resolve Google News links to the original publishers' article URLs."""
    requests = []
    for index, (_, google_url) in enumerate(headlines):
        token, timestamp, signature = get_decoding_parameters(google_url)
        article_request = [
            "garturlreq",
            [
                [
                    "X",
                    "X",
                    ["X", "X"],
                    None,
                    None,
                    1,
                    1,
                    "US:en",
                    None,
                    1,
                    None,
                    None,
                    None,
                    None,
                    None,
                    0,
                    1,
                ],
                "X",
                "X",
                1,
                [1, 1, 1],
                1,
                1,
                None,
                0,
                0,
                None,
                0,
            ],
            token,
            timestamp,
            signature,
        ]
        requests.append(
            ["Fbv4je", json.dumps(article_request), None, str(index)]
        )

    form_data = urllib.parse.urlencode(
        {"f.req": json.dumps([requests], separators=(",", ":"))}
    ).encode()
    request = urllib.request.Request(
        DECODE_URL,
        data=form_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        response_text = response.read().decode("utf-8")

    _, separator, json_text = response_text.partition("\n\n")
    if not separator:
        raise ValueError("Google News returned an unexpected decoding response")

    publisher_links: dict[int, str] = {}
    for entry in json.loads(json_text):
        if len(entry) < 7 or entry[0] != "wrb.fr" or not entry[2]:
            continue
        decoded = json.loads(entry[2])
        if len(decoded) < 2 or decoded[0] != "garturlres":
            continue
        publisher_links[int(entry[6])] = decoded[1]

    resolved: list[tuple[str, str]] = []
    for index, (headline, _) in enumerate(headlines):
        publisher_url = publisher_links.get(index)
        parsed_url = urllib.parse.urlparse(publisher_url or "")
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.hostname == "news.google.com"
        ):
            raise ValueError(f"Could not resolve publisher link for: {headline}")
        resolved.append((headline, publisher_url))
    return resolved


def fetch_headlines(feed_url: str, limit: int = 10) -> list[tuple[str, str]]:
    """Return up to ``limit`` headline/link pairs from a Google News RSS feed."""
    request = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        feed = response.read()

    root = ET.fromstring(feed)
    headlines: list[tuple[str, str]] = []

    for item in root.findall("./channel/item"):
        title = item.findtext("title", default="").strip()
        source = item.findtext("source", default="").strip()
        source_suffix = f" - {source}"
        if source and title.endswith(source_suffix):
            title = title[: -len(source_suffix)].rstrip()
        link = item.findtext("link", default="").strip()
        if title and link:
            headlines.append((title, link))
        if len(headlines) == limit:
            break

    return resolve_publisher_links(headlines) if headlines else []


def write_csv(headlines: list[tuple[str, str]], output_path: Path) -> None:
    """Write headline/link pairs to ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(headlines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch the top Google News headlines and save them as CSV."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"CSV output path (default: {DEFAULT_OUTPUT})",
    )
    feed_group = parser.add_mutually_exclusive_group()
    feed_group.add_argument(
        "--feed-url",
        help="Use a custom Google News RSS URL",
    )
    feed_group.add_argument(
        "--global",
        "--world",
        dest="global_news",
        action="store_true",
        help="Fetch headlines from the Google News World section",
    )
    feed_group.add_argument(
        "--date",
        dest="news_date",
        type=parse_news_date,
        metavar="YYYY-MM-DD",
        help="Fetch a date-filtered Google News search (not a rankings snapshot)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    feed_url = (
        dated_feed_url(args.news_date)
        if args.news_date
        else GLOBAL_FEED_URL
        if args.global_news
        else args.feed_url or DEFAULT_FEED_URL
    )
    try:
        headlines = fetch_headlines(feed_url)
    except (
        urllib.error.URLError,
        TimeoutError,
        ET.ParseError,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        print(f"Could not fetch Google News: {error}", file=sys.stderr)
        return 1

    if not headlines:
        print("Google News returned no headlines.", file=sys.stderr)
        return 1

    write_csv(headlines, args.output)
    print(f"Saved {len(headlines)} headlines to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
