from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import make_bobnews


def sample_ideas() -> list[make_bobnews.NewsIdea]:
    return [
        make_bobnews.NewsIdea(
            "Headline zero", "I did the first silly thing", "url0", "2026-09-10"
        ),
        make_bobnews.NewsIdea(
            "Headline one", "I did the second silly thing", "url1", "2026-09-10"
        ),
        make_bobnews.NewsIdea(
            "Headline two", "I did the third silly thing", "url2", "2026-09-10"
        ),
    ]


class RankingTests(unittest.TestCase):
    @patch("make_bobnews.run_codex_json", return_value={"ranking": [2, 0, 1]})
    def test_orders_candidates_from_structured_response(self, run_codex_json) -> None:
        ranked = make_bobnews.rank_candidates(sample_ideas(), "test-model")

        self.assertEqual(
            [idea.original_headline for idea in ranked],
            ["Headline two", "Headline zero", "Headline one"],
        )
        call = run_codex_json.call_args
        self.assertEqual(call.args[2], make_bobnews.RANKING_SCHEMA)
        self.assertEqual(
            call.args[1]["candidates"][0]["id"], 0
        )
        self.assertEqual(call.kwargs["model"], "test-model")

    @patch("make_bobnews.run_codex_json")
    def test_retries_an_incomplete_ranking(self, run_codex_json) -> None:
        run_codex_json.side_effect = [
            {"ranking": [0, 0]},
            {"ranking": [1, 2, 0]},
        ]

        ranked = make_bobnews.rank_candidates(sample_ideas(), "test-model")

        self.assertEqual(
            [idea.original_headline for idea in ranked],
            ["Headline one", "Headline two", "Headline zero"],
        )
        retry = run_codex_json.call_args_list[1].args[1]
        self.assertIn("each ID", retry["problem_to_fix"])

    def test_rejects_boolean_candidate_ids(self) -> None:
        self.assertEqual(
            make_bobnews.ranking_problem([0, True, 2], 3),
            "ranking contained a non-integer ID",
        )


class GenerationTests(unittest.TestCase):
    @patch("make_bobnews.run_codex_json")
    def test_generates_every_candidate_with_one_fetch_date(
        self, run_codex_json
    ) -> None:
        run_codex_json.return_value = {
            "quotes": [
                {"id": 0, "anecdote": "I once did the first very silly thing"},
                {"id": 1, "anecdote": "I once did another surprisingly silly thing"},
            ]
        }

        ideas = make_bobnews.generate_candidates(
            [("First", "url1"), ("Second", "url2")],
            model="test-model",
            fetch_date="2026-09-10",
        )

        self.assertEqual([idea.fetch_date for idea in ideas], ["2026-09-10"] * 2)
        self.assertEqual(run_codex_json.call_count, 1)
        headlines = run_codex_json.call_args.args[1]["headlines"]
        self.assertEqual(
            headlines,
            [
                {"id": 0, "headline": "First"},
                {"id": 1, "headline": "Second"},
            ],
        )


class OutputTests(unittest.TestCase):
    @patch("make_bobnews.add_caption")
    def test_creates_only_top_k_memes(self, add_caption) -> None:
        ideas = sample_ideas()

        make_bobnews.create_memes(
            ideas,
            top_k=2,
            input_path=Path("clean.jpg"),
            meme_dir=Path("images"),
            font_path="font.ttf",
            size_spec=None,
            uppercase=True,
        )

        self.assertEqual(add_caption.call_count, 2)
        self.assertEqual(
            ideas[0].meme_filename,
            "2026-09-10-01-headline-zero.jpg",
        )
        self.assertEqual(
            ideas[1].meme_filename,
            "2026-09-10-02-headline-one.jpg",
        )
        self.assertEqual(ideas[2].meme_filename, "")

    def test_writes_ranked_csv_with_exact_columns(self) -> None:
        ideas = sample_ideas()
        ideas[0].meme_filename = "winner.jpg"

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.csv"
            make_bobnews.write_results_csv(ideas, output)
            with output.open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(
            list(rows[0]),
            [
                "original_headline",
                "anecdote",
                "meme_filename",
                "story_link",
                "date",
            ],
        )
        self.assertEqual(rows[0]["meme_filename"], "winner.jpg")
        self.assertEqual(rows[0]["date"], "2026-09-10")
        self.assertEqual(rows[1]["meme_filename"], "")


class DefaultsTests(unittest.TestCase):
    def test_defaults_to_ten_memes(self) -> None:
        self.assertEqual(make_bobnews.parse_args([]).top_k, 10)

    def test_defaults_to_world_news(self) -> None:
        self.assertEqual(
            make_bobnews.parse_args([]).feed_url,
            make_bobnews.GLOBAL_FEED_URL,
        )
        self.assertEqual(
            make_bobnews.parse_args(["--uk"]).feed_url,
            make_bobnews.DEFAULT_FEED_URL,
        )

    def test_uses_dated_output_path(self) -> None:
        self.assertEqual(
            make_bobnews.default_output_path(date(2026, 9, 10)),
            Path("out/2026-09-10-output.csv"),
        )

    def test_pipeline_defaults_to_both_dated_csv_paths(self) -> None:
        args = make_bobnews.parse_args([])
        today = date.today().isoformat()
        self.assertEqual(args.output, Path(f"out/{today}-output.csv"))
        self.assertEqual(
            args.headlines_output,
            Path(f"out/{today}-headlines.csv"),
        )

    @patch("make_bobnews.run", side_effect=Exception("something went wrong"))
    def test_main_reports_pipeline_errors_without_a_traceback(self, run) -> None:
        stderr = StringIO()
        with patch("sys.stderr", stderr):
            status = make_bobnews.main([])

        self.assertEqual(status, 1)
        self.assertEqual(stderr.getvalue(), "Error: something went wrong\n")


if __name__ == "__main__":
    unittest.main()
