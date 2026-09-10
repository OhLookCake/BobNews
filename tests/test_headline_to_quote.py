from __future__ import annotations

import io
import unittest
from unittest.mock import patch

import headline_to_quote


class CleanQuoteTests(unittest.TestCase):
    def test_removes_surrounding_quotes_and_extra_whitespace(self) -> None:
        result = headline_to_quote.clean_quote(
            '  “I once misplaced a canal, upsetting several accountants”\n'
        )
        self.assertEqual(
            result, "I once misplaced a canal, upsetting several accountants"
        )

    def test_reports_non_first_person_output(self) -> None:
        self.assertEqual(
            headline_to_quote.quote_problem("He once misplaced an aircraft carrier"),
            'the response did not begin with "I"',
        )

    def test_reports_multiple_sentences(self) -> None:
        self.assertEqual(
            headline_to_quote.quote_problem(
                "I once misplaced an aircraft carrier. It became quite expensive."
            ),
            "the response contained more than one sentence",
        )


class GenerateQuoteTests(unittest.TestCase):
    @patch("headline_to_quote.run_codex_json")
    def test_sends_only_the_headline_as_story_source(self, run_codex_json) -> None:
        run_codex_json.return_value = {
            "quote": "I once offered everyone a fiver so they would keep me employed"
        }

        result = headline_to_quote.generate_quote(
            "Politician promises voters a cash payment"
        )

        self.assertEqual(
            result, "I once offered everyone a fiver so they would keep me employed"
        )
        self.assertEqual(
            run_codex_json.call_args.args[1],
            {"headline": "Politician promises voters a cash payment"},
        )
        self.assertEqual(
            run_codex_json.call_args.args[2], headline_to_quote.QUOTE_SCHEMA
        )
        self.assertIn("Do not research", run_codex_json.call_args.args[0])

    @patch("headline_to_quote.run_codex_json")
    def test_retries_an_invalid_response_once(self, run_codex_json) -> None:
        run_codex_json.side_effect = [
            {"quote": "A ship was parked rather badly"},
            {
                "quote": (
                    "I once parked my ship badly and inconvenienced the entire planet"
                )
            },
        ]

        result = headline_to_quote.generate_quote("Ship blocks canal")

        self.assertEqual(
            result,
            "I once parked my ship badly and inconvenienced the entire planet",
        )
        retry_input = run_codex_json.call_args_list[1].args[1]
        self.assertEqual(retry_input["headline"], "Ship blocks canal")
        self.assertIn("did not begin", retry_input["problem_to_fix"])

    @patch("headline_to_quote.run_codex_json")
    def test_raises_after_repeated_invalid_responses(self, run_codex_json) -> None:
        run_codex_json.side_effect = [
            {"quote": "Too vague"},
            {"quote": "Still too vague"},
        ]
        with self.assertRaises(headline_to_quote.QuoteGenerationError):
            headline_to_quote.generate_quote("Some headline")


class MainTests(unittest.TestCase):
    @patch("headline_to_quote.generate_quote")
    def test_prints_generated_quote(self, generate_quote) -> None:
        generate_quote.return_value = "I once caused a diplomatic incident with a kite"
        stdout = io.StringIO()

        with patch("sys.stdout", stdout):
            status = headline_to_quote.main(["Diplomatic kite incident"])

        self.assertEqual(status, 0)
        self.assertEqual(
            stdout.getvalue(), "I once caused a diplomatic incident with a kite\n"
        )


if __name__ == "__main__":
    unittest.main()
