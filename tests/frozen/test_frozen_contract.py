"""Check the frozen labels without a ladder or agent run."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import tomllib
import unittest

from tests.frozen.harness import make_lab


HERE = Path(__file__).resolve().parent
FROZEN_CONTRACTS_SHA256 = "815030414fced55f5dc1d08f25ed417c221ed32ed8845493823bebee2fd8aeb9"


class FrozenContractTests(unittest.TestCase):
    def test_contracts_file_matches_the_frozen_hash(self):
        # A change after B1 starts needs Ahmed's yes and a dated addendum, so this hash moves only then.
        # The one allowed edit so far: B1 filled replay_cases.timeout_control (2026-11-15).
        digest = hashlib.sha256((HERE / "contracts.json").read_bytes()).hexdigest()
        self.assertEqual(digest, FROZEN_CONTRACTS_SHA256)

    def test_replay_case_ids_and_b1_ids_are_unique(self):
        contracts = json.loads((HERE / "contracts.json").read_text(encoding="utf-8"))
        replay = contracts["replay_cases"]
        cases = replay["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(replay["b1_cases"]), len(set(replay["b1_cases"])))
        self.assertTrue(set(replay["b1_cases"]).issubset(ids))

    def test_replay_commands_agree_with_lab_tasks(self):
        contracts = json.loads((HERE / "contracts.json").read_text(encoding="utf-8"))
        cases = contracts["replay_cases"]["cases"]
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory) / "lab"
            make_lab(lab)
            config = tomllib.loads((lab / "ladder.toml").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["id"]):
                command = case["argv"][0]
                if command == "gates":
                    self.assertIn("gates", config)
                elif command == "nosuch":
                    self.assertNotIn(command, config["tasks"])
                else:
                    self.assertIn(command, config["tasks"])

    def test_sample_has_exact_source_and_no_call_text(self):
        sample = json.loads((HERE / "claude_sample.json").read_text(encoding="utf-8"))
        self.assertEqual(set(sample), {"frozen_on", "source", "slots"})
        self.assertEqual(sample["frozen_on"], "2026-11-15")
        source = sample["source"]
        self.assertEqual(source, {
            "repo": "DevOps",
            "file": "research/transcript-audit-2026-11-15.json",
            "file_last_commit": "3c57abd",
            "sha256": "40c540fd3307c9d2191d8466330de44db082b1317282f16c4517c70d13505fa9",
            "generated_utc": "2026-11-15T12:37:09.076Z",
            "metric": "by_source.claude.pipe_tax, keys that start with 'ladder>'",
            "agent": "claude only (no Codex)",
            "window": (
                "all Claude transcripts from 2026-08-06 to the generation time of the source file; "
                "transcripts grew after it, so a later re-run may count more"
            ),
            "claude_ladder_calls_total": 103,
            "piped_total": 46,
            "sink_counts": {
                "tail": 18, "Select-Object": 12, "head": 10,
                "grep": 4, "sed": 1, "Select-String": 1,
            },
            "note": (
                "by_source.claude.pipe_any gives 44 (Select-Object 10, not 12); the 46 follows pipe_tax. "
                "Per-call need labels and fixture ids are ___ until ticket 14b (B6a) exports them; "
                "B6a fills only the need and fixture_id fields."
            ),
            "allowed_need": ["result", "error_line", "full_log", "count", "other"],
        })
        slots = sample["slots"]
        self.assertEqual([slot["id"] for slot in slots],
                         [f"C-{number:03d}" for number in range(1, source["piped_total"] + 1)])
        self.assertEqual(Counter(slot["sink"] for slot in slots), source["sink_counts"])
        for slot in slots:
            with self.subTest(slot=slot["id"]):
                self.assertEqual(set(slot), {"id", "sink", "need", "fixture_id"})
                self.assertIn(slot["need"], [None, *source["allowed_need"]])
                self.assertIsNone(slot["need"])
                self.assertIsNone(slot["fixture_id"])
        # The 2 fixed source descriptions exceed 120 characters. Their exact
        # values above take priority; all other strings stay short labels.
        def check_strings(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertLessEqual(len(key), 120)
                    check_strings(child, (*path, key))
            elif isinstance(value, list):
                for child in value:
                    check_strings(child, path)
            elif isinstance(value, str) and path not in {
                ("source", "window"), ("source", "note"),
            }:
                self.assertLessEqual(len(value), 120, path)
        check_strings(sample)


if __name__ == "__main__":
    unittest.main()
