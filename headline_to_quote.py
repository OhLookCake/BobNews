#!/usr/bin/env python3
"""Turn a news headline into a surreal first-person panel-show quote."""

from __future__ import annotations

import argparse
import os
import re
import sys

from codex_runner import run_codex_json


DEFAULT_MODEL = os.environ.get("CODEX_MODEL")
MAX_ATTEMPTS = 2

QUOTE_SCHEMA = {
    "type": "object",
    "properties": {"quote": {"type": "string"}},
    "required": ["quote"],
    "additionalProperties": False,
}

STYLE_INSTRUCTIONS = """\
Turn each supplied news headline into a short, funny, first-person claim that could
appear on a British truth-or-lie panel-show card. Aim for surreal specificity,
cheerful understatement, and a ridiculous mismatch between an ordinary action
and an enormous consequence. Do not imitate or mention any real performer.

This is a headline transformation, not a reporting task. Use only the supplied
headline. Do not research, browse, rely on background knowledge, or add alleged
facts about the story.

Rules for every quote:
- Use one line, with no label or surrounding quotation marks.
- Begin with "I" and write entirely in the first person.
- Use roughly 8 to 24 words.
- Keep the headline's central premise recognizable, but discard most names,
  locations, exact figures, and news jargon.
- You may speak as either the actor or the person affected by the event.
- You may invent an absurd possible cause or aftermath, provided it is clearly a
  comic transformation rather than a new factual claim.
- Prefer a mundane verb, object, hobby, errand, misunderstanding, or small gift
  paired with a wildly disproportionate result.
- Pique curiosity; do not explain the joke.
- For headlines involving death or serious suffering, make the absurdity adjacent
  to the event and never target victims or their suffering.

Examples:
Headline: Massive cargo ship turns sideways, blocks Egypt's Suez Canal costing
global trade between $6bn and $10bn a day
Output: I once parked my ship wrong, breaking down global trade

Headline: NATO scrambles fighter jets as Russia launches massive 'air attack' -
WW3 fears explode
Output: I once incited WW3 playing with my electronic toys

Headline: Trump says every adult American would get $5,000 if Republicans win
midterms
Output: I once successfully bribed an entire country to win an election
"""

INSTRUCTIONS = STYLE_INSTRUCTIONS + """

The input contains one headline. Return exactly one quote in the `quote` field.
Do not use tools or inspect files; answer solely from the input JSON.
"""

FIRST_PERSON = re.compile(r"^I(?:\b|['’])")
SURROUNDING_QUOTES = (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"))


class QuoteGenerationError(RuntimeError):
    """Raised when a usable quote cannot be generated."""


def clean_quote(text: str) -> str:
    """Normalize harmless model formatting around a generated quote."""
    quote = " ".join(text.strip().split())
    for opening, closing in SURROUNDING_QUOTES:
        if quote.startswith(opening) and quote.endswith(closing) and len(quote) > 1:
            quote = quote[len(opening) : -len(closing)].strip()
            break
    return quote


def quote_problem(quote: str) -> str | None:
    """Return why a quote is invalid, or ``None`` when it meets the contract."""
    if not quote:
        return "the response was empty"
    if not FIRST_PERSON.match(quote):
        return 'the response did not begin with "I"'

    word_count = len(quote.split())
    if word_count < 6:
        return "the response was too short"
    if word_count > 30:
        return "the response was too long"
    if len(quote) > 240:
        return "the response was too long"
    if re.search(r"[.!?]\s+\S", quote):
        return "the response contained more than one sentence"
    return None


def generate_quote(
    headline: str,
    model: str | None = DEFAULT_MODEL,
    max_attempts: int = MAX_ATTEMPTS,
) -> str:
    """Generate and validate a quote using only ``headline`` as source material."""
    if not headline.strip():
        raise ValueError("Headline cannot be empty.")

    previous_attempt = ""
    previous_problem = ""
    for attempt in range(max_attempts):
        request_data = {"headline": headline.strip()}
        if attempt:
            request_data.update(
                {
                    "previous_attempt": previous_attempt,
                    "problem_to_fix": previous_problem,
                }
            )

        response = run_codex_json(
            INSTRUCTIONS,
            request_data,
            QUOTE_SCHEMA,
            model=model,
        )
        quote = clean_quote(response.get("quote", ""))
        problem = quote_problem(quote)
        if problem is None:
            return quote
        previous_attempt = quote
        previous_problem = problem

    raise QuoteGenerationError(
        f"The model did not return a valid first-person quote: {previous_problem}."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Turn a news headline into a surreal first-person quote."
    )
    parser.add_argument(
        "headline",
        nargs="*",
        help="Headline to transform (may also be piped through stdin)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Codex model override (default: CODEX_MODEL or Codex configuration)",
    )
    return parser.parse_args(argv)


def read_headline(parts: list[str]) -> str:
    """Read a headline from arguments, falling back to redirected stdin."""
    headline = " ".join(parts).strip()
    if headline:
        return headline
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return ""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    headline = read_headline(args.headline)
    if not headline:
        print(
            "Error: provide a headline as an argument or through stdin.",
            file=sys.stderr,
        )
        return 2

    try:
        quote = generate_quote(headline, model=args.model)
    except (QuoteGenerationError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Codex failed: {error}", file=sys.stderr)
        return 1

    print(quote)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
