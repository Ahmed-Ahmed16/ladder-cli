"""Fast canned-result tests for the frozen scoring contract."""

import json
import tempfile
import unittest
from pathlib import Path

from . import scoring
from .harness import RunResult


CONTRACT = json.loads(Path(__file__).with_name("contracts.json").read_text(encoding="utf-8"))

MODE_CELLS = (
    ("yes", "set", "none", "human", True),
    ("yes", "set", "LADDER_AGENT=1", "agent", False),
    ("yes", "set", "LADDER_AGENT=0", "human", True),
    ("yes", "unset", "none", "human", True),
    ("yes", "unset", "LADDER_AGENT=1", "agent", False),
    ("yes", "unset", "LADDER_AGENT=0", "human", True),
    ("no", "set", "none", "agent", False),
    ("no", "set", "LADDER_AGENT=1", "agent", False),
    ("no", "set", "LADDER_AGENT=0", "human", True),
    ("no", "unset", "none", "human", True),
    ("no", "unset", "LADDER_AGENT=1", "agent", False),
    ("no", "unset", "LADDER_AGENT=0", "human", True),
)


class FrozenScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ladder-frozen-scoring-")
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / "child output with spaces.log"
        self.log.write_text(
            "ERROR-database-not-found\nERROR-lint-failed\nERROR-synthetic-at-150\n",
            encoding="utf-8",
        )
        self.cases = {case["id"]: case for case in CONTRACT["replay_cases"]["cases"]}
        self.b3 = CONTRACT["builds"]["B3a_B3b"]["replay"]
        self.pr = CONTRACT["pr_replay"]["per_state"]

    def failure(self, exit_code=1, prefix="ladder: FAIL"):
        return RunResult(exit_code, [f'{prefix} log: "{self.log}"'])

    def test_last_line_class_table(self):
        for line, expected in [
            ("", "empty"), ("  ", "empty"),
            ("ladder: FAIL task", "fail_line"),
            ("PASS and FAIL", "fail_line"),
            ("FAILED child", "child_line"),
            ("ladder: ok task", "ok_line"),
            ("gates: all 3 steps passed", "ok_line"),
            ("suite PASS", "ok_line"),
            ("PASSWORD", "child_line"),
            ("PASSED", "child_line"),
            ("FAILED to read PASSWORD file", "child_line"),
            ("showing 40 of 200", "cut_line"),
            ("160 lines cut", "cut_line"),
            ("child output", "child_line"),
        ]:
            with self.subTest(line=line):
                self.assertEqual(scoring.last_line_class(line), expected)

    def test_extract_log_path_handles_quotes_and_spaces(self):
        for line in [str(self.log), f'log: "{self.log}"', f"FAIL log='{self.log}'", f"FAIL log: {self.log}"]:
            with self.subTest(line=line):
                self.assertEqual(scoring.extract_log_path([line]), self.log)

    def test_extract_log_path_searches_last3_nonempty_lines(self):
        self.assertEqual(scoring.extract_log_path([str(self.log), "", "a", "", "b"]), self.log)
        self.assertIsNone(scoring.extract_log_path([str(self.log), "a", "b", "c"]))

    def test_extract_log_path_rejects_missing_files_and_wrong_suffix(self):
        self.assertIsNone(scoring.extract_log_path([str(self.log) + ".missing"]))
        self.assertIsNone(scoring.extract_log_path([str(self.log.with_name("missing.log"))]))

    def test_extract_log_path_uses_last_existing_path(self):
        later = Path(self.temp.name) / "later.log"
        later.write_text("x", encoding="utf-8")
        self.assertEqual(scoring.extract_log_path([str(self.log), str(later)]), later)

    def test_all_replay_cases_have_positive_examples(self):
        for case_id, spec in self.cases.items():
            if case_id == "gates_dry_run":
                result = RunResult(0, ["step1", "step2", "step3"])
            elif case_id == "nosuch":
                result = RunResult(1, ["ladder: unknown job or task: nosuch"])
            elif case_id == "long":
                result = RunResult(0, ["child output", "ladder: ok"])
            else:
                code = 1 if spec["expect_exit"] == "nonzero" else spec["expect_exit"]
                result = self.failure(code, "ladder: FAIL timeout" if case_id == "timeout" else "ladder: FAIL")
            with self.subTest(case=case_id):
                score = scoring.score_replay_case(spec, result)
                self.assertEqual(score["status"], "PASS")
                self.assertFalse(score["false_success"])
                self.assertTrue(all(type(value) is bool for value in score["checks"].values()))
                self.assertEqual(set(score["observed"]), {"exit_code", "line_count", "last_line_class", "timed_out"})

    def test_replay_exit_zero_or_success_last_line_fails_with_false_success(self):
        for result in [self.failure(0), RunResult(3, self.failure(3).lines + ["ladder: ok"]), RunResult(3, self.failure(3).lines + ["PASS"])]:
            with self.subTest(result=result):
                score = scoring.score_replay_case(self.cases["fail"], result)
                self.assertEqual(score["status"], "FAIL")
                self.assertTrue(score["false_success"])

    def test_pipe_exit_zero_fails_with_false_success(self):
        pipe = scoring.score_replay_case(self.cases["pipe"], RunResult(0, ["line 2 of 2"]))
        self.assertEqual(pipe["status"], "FAIL")
        self.assertTrue(pipe["false_success"])

    def test_replay_missing_or_old_fail_summary_and_log_fail(self):
        for lines in [["child error"], [str(self.log)], ["FAIL"], self.failure(3).lines + ["a", "b", "c"]]:
            with self.subTest(lines=lines):
                score = scoring.score_replay_case(self.cases["fail"], RunResult(3, lines))
                self.assertEqual(score["status"], "FAIL")
                self.assertFalse(score["false_success"])

    def test_replay_wrong_error_in_log_fails(self):
        self.log.write_text("unrelated output", encoding="utf-8")
        score = scoring.score_replay_case(self.cases["longfail"], self.failure())
        self.assertEqual(score["status"], "FAIL")
        self.assertFalse(score["checks"]["log_contains"])

    def test_replay_timeout_is_fail_without_false_success(self):
        result = RunResult(0, ["PASS"], True)
        score = scoring.score_replay_case(self.cases["timeout"], result)
        self.assertEqual(score["status"], "FAIL")
        self.assertFalse(score["false_success"])
        self.assertTrue(score["observed"]["timed_out"])

    def test_replay_timeout_needs_word_in_last3(self):
        score = scoring.score_replay_case(self.cases["timeout"], self.failure())
        self.assertEqual(score["status"], "FAIL")
        self.assertFalse(score["checks"]["last3_word"])

    def test_unknown_task_observables(self):
        for result in [RunResult(1, ["bad command"]), RunResult(1, ["unknown job or task", "extra"])]:
            with self.subTest(result=result):
                score = scoring.score_replay_case(self.cases["nosuch"], result)
                self.assertEqual(score["status"], "FAIL")
                self.assertNotIn("fail_summary", score["checks"])
                self.assertNotIn("log_path", score["checks"])

    def test_replay_explicit_no_fail_summary_allows_plain_failure(self):
        spec = {"id": "plain_error", "expect_exit": 1, "must_fail": True,
                "no_fail_summary": True}
        score = scoring.score_replay_case(spec, RunResult(1, ["child error"]))
        self.assertEqual(score["status"], "PASS")
        self.assertNotIn("fail_summary", score["checks"])
        self.assertNotIn("log_path", score["checks"])

    def test_replay_text_and_line_contract_defaults_to_no_fail_summary(self):
        spec = {"id": "missing_task", "expect_exit": 1, "must_fail": True,
                "expect_text": "unknown task", "expect_lines": 1}
        score = scoring.score_replay_case(spec, RunResult(1, ["unknown task"]))
        self.assertEqual(score["status"], "PASS")
        self.assertNotIn("fail_summary", score["checks"])
        self.assertNotIn("log_path", score["checks"])

    def test_replay_explicit_false_requires_fail_summary_and_log(self):
        spec = {**self.cases["nosuch"], "no_fail_summary": False}
        score = scoring.score_replay_case(spec, RunResult(1, ["unknown job or task"]))
        self.assertEqual(score["status"], "FAIL")
        self.assertFalse(score["checks"]["fail_summary"])
        self.assertFalse(score["checks"]["log_path"])

    def test_gates_dry_run_ignores_using_line_before_three_steps(self):
        lines = ["ladder: using C:/repo/ladder.toml", "1. lint", "2. test", "3. build"]
        score = scoring.score_replay_case(self.cases["gates_dry_run"], RunResult(0, lines))
        self.assertEqual(score["status"], "PASS")
        self.assertTrue(score["checks"]["line_count"])

    def test_gates_dry_run_rejects_four_steps_after_using_line(self):
        lines = ["ladder: using C:/repo/ladder.toml", "1. lint", "2. test", "3. build", "4. extra"]
        score = scoring.score_replay_case(self.cases["gates_dry_run"], RunResult(0, lines))
        self.assertEqual(score["status"], "FAIL")
        self.assertFalse(score["checks"]["line_count"])

    def test_expected_mode_matches_literal_matrix_cells(self):
        for tty, claude, override, mode, _using_line in MODE_CELLS:
            cell = {"tty": tty, "claudecode": claude, "override": override}
            with self.subTest(cell=cell):
                self.assertEqual(scoring.expected_mode(cell), mode)

    def test_matrix_pipe_cells_pass_and_tty_cells_are_not_run(self):
        for tty, claude, override, mode, using_line in MODE_CELLS:
            cell = {"tty": tty, "claudecode": claude, "override": override}
            doctor = RunResult(1, ["ok   mode: " + mode + " (details)"])
            dryrun = RunResult(0, ["ladder: using C:/repo/ladder.toml"] if using_line else [])
            with self.subTest(cell=cell):
                score = scoring.score_matrix_cell(cell, doctor, dryrun)
                self.assertEqual(score["status"], "NOT_RUN" if tty == "yes" else "PASS")
                if tty == "yes":
                    self.assertEqual(score["reason"], "no_pty")

    def test_matrix_rejects_wrong_mode_using_line_or_timeout(self):
        cell = {"tty": "no", "claudecode": "set", "override": "none"}
        for doctor, dryrun in [
            (RunResult(0, ["ok   mode: human"]), RunResult(0, [])),
            (RunResult(0, ["mode: agent"]), RunResult(0, [])),
            (RunResult(0, ["ok   mode: agent"]), RunResult(0, ["ladder: using x"])),
            (RunResult(0, ["ok   mode: agent"], True), RunResult(0, [])),
        ]:
            with self.subTest(doctor=doctor, dryrun=dryrun):
                self.assertEqual(scoring.score_matrix_cell(cell, doctor, dryrun)["status"], "FAIL")

    def test_matrix_human_override_requires_using_line(self):
        cell = {"tty": "no", "claudecode": "set", "override": "LADDER_AGENT=0"}
        self.assertEqual(scoring.score_matrix_cell(cell, RunResult(0, ["ok   mode: human"]), RunResult(0, []))["status"], "FAIL")

    def test_b3_long_needs_cut_and_existing_path_on_same_line(self):
        spec = self.b3["long_agent_mode"]
        good = f'showing 40 of 200; log: "{self.log}"'
        self.assertEqual(scoring.score_b3(spec, RunResult(0, [good, "ladder: ok"]))["status"], "PASS")
        for lines in [
            ["child", str(self.log)],
            ["showing 40 of 200", str(self.log)],
            ["showing 40 of 200; missing.log"],
            [good] + ["child"] * spec["max_total_lines"],
        ]:
            with self.subTest(lines=lines):
                self.assertEqual(scoring.score_b3(spec, RunResult(0, lines))["status"], "FAIL")

    def test_b3_longfail_checks_log_result_contract(self):
        spec = self.b3["longfail150_agent_mode"]
        result = self.failure()
        good_log = RunResult(0, ["FAILED test_widget_rounding: ERROR-synthetic-at-150"])
        self.assertEqual(scoring.score_b3(spec, result, good_log)["status"], "PASS")
        for log_result in [None, RunResult(1, good_log.lines), RunResult(0, ["other"]), RunResult(0, good_log.lines * 11), RunResult(0, good_log.lines, True)]:
            with self.subTest(log_result=log_result):
                self.assertEqual(scoring.score_b3(spec, result, log_result)["status"], "FAIL")

    def test_b3_longfail_reports_no_log_path(self):
        spec = self.b3["longfail150_agent_mode"]
        good_log = RunResult(0, ["FAILED test_widget_rounding: ERROR-synthetic-at-150"])
        score = scoring.score_b3(spec, RunResult(1, ["FAIL"]), good_log)
        self.assertEqual(score["reason"], "no_log_path")
        self.assertEqual(score["status"], "FAIL")

    def test_b3_longfail_exit_zero_is_false_success(self):
        spec = self.b3["longfail150_agent_mode"]
        good_log = RunResult(0, ["FAILED test_widget_rounding: ERROR-synthetic-at-150"])
        score = scoring.score_b3(spec, self.failure(0), good_log)
        self.assertEqual(score["status"], "FAIL")
        self.assertTrue(score["false_success"])

    def test_b3_longfail_rejects_output_over_line_cap(self):
        spec = self.b3["longfail150_agent_mode"]
        good_log = RunResult(0, ["FAILED test_widget_rounding: ERROR-synthetic-at-150"])
        result = RunResult(1, ["child"] * spec["max_total_lines"] + self.failure().lines)
        score = scoring.score_b3(spec, result, good_log)
        self.assertEqual(score["status"], "FAIL")
        self.assertFalse(score["checks"]["line_cap"])

    def test_all_pr_states_positive_and_case_insensitive(self):
        for state_id, spec in self.pr.items():
            output = spec.get("must_contain", []) or ["PR data"]
            result = RunResult(1 if spec["expect_exit"] == "nonzero" else spec["expect_exit"], [line.upper() for line in output])
            with self.subTest(state=state_id):
                score = scoring.score_pr_state(state_id, spec, result)
                self.assertEqual(score["status"], "PASS")
                self.assertFalse(score["false_success"])

    def test_pr_exit_zero_without_failed_check_is_false_success(self):
        for state_id in ("pr-one-failed", "pr-log-missing", "pr-api-error"):
            with self.subTest(state=state_id):
                score = scoring.score_pr_state(state_id, self.pr[state_id], RunResult(0, ["green"]))
                self.assertEqual(score["status"], "FAIL")
                self.assertTrue(score["false_success"])

    def test_pr_other_missing_observables_fail_without_false_success(self):
        for state_id, result in [
            ("pr-green", RunResult(0, [])),
            ("pr-one-failed", RunResult(0, ["unit-tests"])),
            ("pr-review-pending", RunResult(0, ["no review data"])),
            ("pr-no-checks", RunResult(0, ["unknown"])),
            ("pr-api-error", RunResult(1, ["error"] * 4)),
            ("pr-api-error", RunResult(0, ["green"], True)),
        ]:
            with self.subTest(state=state_id, result=result):
                score = scoring.score_pr_state(state_id, self.pr[state_id], result)
                self.assertEqual(score["status"], "FAIL")
                self.assertFalse(score["false_success"])

    def test_build_verdict_counts_and_exact_keys(self):
        samples = [
            ([{"status": "PASS"}], True, (1, 0, 0, 0)),
            ([{"status": "FAIL"}], False, (0, 1, 0, 0)),
            ([{"status": "NOT_RUN", "reason": "no_pty"}], True, (0, 0, 1, 0)),
            ([{"status": "NOT_RUN", "reason": "missing_executable"}], False, (0, 0, 1, 0)),
            ([{"status": "PASS", "false_success": True}], False, (1, 0, 0, 1)),
            ([{"status": "PASS"}, {"status": "PASS"},
              {"status": "FAIL", "false_success": True},
              {"status": "NOT_RUN", "reason": "no_pty"},
              {"status": "NOT_RUN", "reason": "missing"}], False, (2, 1, 2, 1)),
        ]
        keys = {"pass", "pass_count", "fail_count", "not_run_count", "false_success_count"}
        for scores, expected_pass, counts in samples:
            for supplied in (scores, {str(i): score for i, score in enumerate(scores)}, iter(scores)):
                with self.subTest(scores=scores, kind=type(supplied)):
                    verdict = scoring.build_verdict(supplied)
                    self.assertEqual(set(verdict), keys)
                    self.assertEqual(verdict["pass"], expected_pass)
                    self.assertEqual(tuple(verdict[key] for key in ("pass_count", "fail_count", "not_run_count", "false_success_count")), counts)

    def test_scores_store_only_safe_observations(self):
        secret = CONTRACT["privacy"]["fake_secret_marker"]
        result = self.failure(3)
        result.lines.insert(0, secret)
        score = scoring.score_replay_case(self.cases["fail"], result)
        stored = json.dumps(score)
        self.assertNotIn(secret, stored)
        self.assertNotIn(str(self.log), stored)


if __name__ == "__main__":
    unittest.main()
