from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_runner


class CodexRunnerTests(unittest.TestCase):
    @patch("codex_runner.shutil.which", return_value="/usr/local/bin/codex")
    @patch("codex_runner.subprocess.run")
    def test_runs_ephemerally_and_reads_structured_output(
        self, subprocess_run, which
    ) -> None:
        def complete(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text('{"answer":"done"}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        subprocess_run.side_effect = complete
        result = codex_runner.run_codex_json(
            "Follow these instructions.",
            {"headline": "Some headline"},
            {"type": "object"},
            model="test-model",
        )

        self.assertEqual(result, {"answer": "done"})
        command = subprocess_run.call_args.args[0]
        self.assertIn("--ephemeral", command)
        self.assertIn("read-only", command)
        self.assertIn("--output-schema", command)
        self.assertEqual(command[-3:], ["--model", "test-model", "-"])
        prompt = subprocess_run.call_args.kwargs["input"]
        self.assertIn(json.dumps({"headline": "Some headline"}), prompt)
        self.assertEqual(subprocess_run.call_args.kwargs["cwd"], Path.cwd())

    @patch.dict(os.environ, {"BOBNEWS_CODEX_BYPASS_SANDBOX": "1"})
    @patch("codex_runner.shutil.which", return_value="/usr/local/bin/codex")
    @patch("codex_runner.subprocess.run")
    def test_supports_explicit_nested_sandbox_bypass(
        self, subprocess_run, which
    ) -> None:
        def complete(command, **kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text('{"answer":"done"}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        subprocess_run.side_effect = complete
        codex_runner.run_codex_json("Do it", {}, {"type": "object"})

        command = subprocess_run.call_args.args[0]
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("--sandbox", command)

    @patch("codex_runner.shutil.which", return_value=None)
    def test_reports_a_missing_codex_executable(self, which) -> None:
        with self.assertRaisesRegex(codex_runner.CodexRunError, "Could not find"):
            codex_runner.run_codex_json("Do it", {}, {"type": "object"})


if __name__ == "__main__":
    unittest.main()
