import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ladder.cli import Context, main
from ladder.process import LadderError, Runner
from ladder.prstatus import status
from tests.test_cli import FakeRunner


FIELDS = ("number,url,state,title,headRefOid,reviewDecision,reviewRequests,"
          "latestReviews,statusCheckRollup")
VIEW = ("gh", "pr", "view", "--json", FIELDS)
LOG = ("gh", "run", "view", "201", "--log-failed")
STATES = Path(__file__).parent / "frozen" / "pr_states"


def frozen_answers(name):
    state = json.loads((STATES / (name + ".json")).read_text(encoding="utf-8"))
    view = next(call for call in state["calls"] if call["match"] == ["pr", "view"])
    log = next(call for call in state["calls"] if call["match"] == list(LOG[1:]))
    answer = LadderError(view["stderr"]) if view["exit"] else view["stdout"]
    return {VIEW: answer, LOG: (log["exit"], log["stdout"])}


def failed(name="unit-tests"):
    return {"name": name, "status": "COMPLETED", "conclusion": "FAILURE",
            "checkSuite": {"workflowRun": {"databaseId": 201}}}


class PRStatusTests(unittest.TestCase):
    def invoke(self, name="pr-green", *, flags=(), changes=None, log=None):
        answers = frozen_answers(name)
        if changes is not None:
            pr = json.loads(answers[VIEW])
            pr.update(changes)
            answers[VIEW] = json.dumps(pr)
        if log is not None:
            answers[LOG] = log
        command = VIEW
        if flags and flags[0].isdecimal():
            command = (*VIEW[:3], flags[0], *VIEW[3:])
            answers[command] = answers.pop(VIEW)
        out, err = io.StringIO(), io.StringIO()
        runner = FakeRunner(out, answers)
        context = Context(runner, out, err, load_config=lambda _: self.fail("config was read"))
        code = main(["pr", "status", *flags], context)
        self.assertIs(runner.out, out)
        return code, out.getvalue().splitlines(), err.getvalue(), runner.commands

    def test_six_frozen_states_through_cli(self):
        cases = {"pr-green": ("green: yes", "review: approved"),
                 "pr-one-failed": ("green: no", "unit-tests", "ERROR-synthetic-unit-failed"),
                 "pr-review-pending": ("green: yes", "pending: synthetic-reviewer"),
                 "pr-no-checks": ("green: unknown", "no checks"),
                 "pr-log-missing": ("green: no", "lint", "log not available"),
                 "pr-api-error": ()}
        for name, expected in cases.items():
            with self.subTest(name=name):
                code, lines, err, commands = self.invoke(name)
                self.assertEqual(code, 1 if name == "pr-api-error" else 0)
                self.assertEqual(commands[0], list(VIEW))
                self.assertLessEqual(len(lines) + len(err.splitlines()), 25)
                for part in expected:
                    self.assertIn(part, "\n".join(lines))
                if name == "pr-api-error":
                    self.assertEqual(lines, [])
                    self.assertLessEqual(len(err.splitlines()), 3)
                else:
                    self.assertEqual(err, "")
                    self.assertEqual(lines[0], "PR #101 OPEN: https://example.invalid/synthetic/pull/101")
                    self.assertEqual(commands, [list(VIEW), list(LOG)] if "failed" in name
                                     or name == "pr-log-missing" else [list(VIEW)])
                    if name != "pr-review-pending":
                        self.assertNotIn("pending", lines[-1])

    def test_pending_and_unknown_shapes_never_give_yes(self):
        checks = [None, {}, {"__typename": "StatusContext", "state": "SUCCESS"},
                  {"name": "queued", "status": "QUEUED", "conclusion": "SUCCESS"},
                  {"name": "running", "status": "IN_PROGRESS"},
                  {"name": "done", "status": "COMPLETED", "conclusion": "UNKNOWN"},
                  {"__typename": "Other", "status": "COMPLETED", "conclusion": "SUCCESS"}]
        for check in checks:
            with self.subTest(check=check):
                code, lines, err, commands = self.invoke(changes={"statusCheckRollup": [check]})
                self.assertEqual((code, err, commands), (0, "", [list(VIEW)]))
                self.assertEqual(lines[1], "green: unknown; checks: 0 failed, 0 passed, 1 pending")
        self.assertIn("green: unknown", self.invoke(changes={"statusCheckRollup": {}})[1][1])

    def test_only_success_neutral_and_skipped_checkruns_count_as_green(self):
        for conclusion in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE",
                           "SUCCESS", "NEUTRAL", "SKIPPED"):
            with self.subTest(conclusion=conclusion):
                check = {**failed(), "conclusion": conclusion}
                code, lines, err, _ = self.invoke(changes={"statusCheckRollup": [check]})
                expected = "yes" if conclusion in {"SUCCESS", "NEUTRAL", "SKIPPED"} else "no"
                self.assertEqual((code, err), (0, ""))
                self.assertIn("green: " + expected, lines[1])

    def test_status_context_failure_lists_a_failed_check_with_unknown_run(self):
        for state, green in (("SUCCESS", "yes"), ("FAILURE", "no"), ("ERROR", "no"),
                             ("PENDING", "unknown"), ("OTHER", "unknown")):
            with self.subTest(state=state):
                check = {"__typename": "StatusContext", "context": "external", "state": state}
                code, lines, err, commands = self.invoke(changes={"statusCheckRollup": [check]})
                self.assertEqual((code, err, commands), (0, "", [list(VIEW)]))
                self.assertIn("green: " + green, lines[1])
                if green == "no":
                    self.assertIn("FAIL external (run unknown)", lines)
                    self.assertIn("  log not available", lines)

    def test_long_failed_log_is_cut_to_10_lines_with_a_marker(self):
        code, lines, _, _ = self.invoke("pr-one-failed")
        self.assertEqual(code, 0)
        self.assertIn("  first error: ERROR-synthetic-unit-failed", lines)
        self.assertIn("  showing 10 of 200 log lines, add --all", lines)
        self.assertNotIn("  synthetic log line 2", lines)

    def test_all_flag_raises_the_log_cut_to_100_lines(self):
        _, lines, _, _ = self.invoke("pr-one-failed", flags=("--all",))
        self.assertIn("  showing 100 of 200 log lines, add --all", lines)
        self.assertIn("  synthetic log line 102", lines)
        self.assertNotIn("  synthetic log line 103", lines)

    def test_short_log_prints_no_cut_marker(self):
        _, lines, _, _ = self.invoke("pr-one-failed", flags=("--all",), log=(0, "ERROR\nlast\n"))
        self.assertNotIn("showing", "\n".join(lines))

    def test_failure_cap_keeps_review_and_total_within_25_lines(self):
        checks = [failed("check-" + str(i)) for i in range(5)]
        _, lines, _, commands = self.invoke(changes={"statusCheckRollup": checks})
        self.assertLessEqual(len(lines), 25)
        self.assertEqual(sum(line.startswith("FAIL ") for line in lines), 3)
        self.assertIn("showing 3 of 5 failed checks, add --all", lines)
        self.assertEqual(lines[-1], "review: approved")
        self.assertEqual(commands, [list(VIEW)] + [list(LOG)] * 3)
        _, lines, _, commands = self.invoke(flags=("--all",), changes={"statusCheckRollup": checks})
        self.assertEqual(sum(line.startswith("FAIL ") for line in lines), 5)
        self.assertEqual(commands, [list(VIEW)] + [list(LOG)] * 5)
        self.assertNotIn("failed checks, add --all", "\n".join(lines))

    def test_log_fallback_and_unavailable_logs(self):
        _, lines, _, _ = self.invoke("pr-one-failed", log=(0, "\nhello\nlast\n"))
        self.assertIn("  first error: hello", lines)
        for log in ((0, ""), (0, " \n\t"), (1, "ERROR should not appear"), LadderError("unavailable")):
            with self.subTest(log=log):
                code, lines, err, _ = self.invoke("pr-one-failed", log=log)
                self.assertEqual((code, err), (0, ""))
                self.assertIn("  log not available", lines)

    def test_database_id_precedes_url_and_url_is_the_fallback(self):
        for nested, expected in (({"workflowRun": {"databaseId": 201}}, "201"), ({}, "201")):
            check = {**failed(), "checkSuite": nested,
                     "detailsUrl": "https://example.invalid/actions/runs/201/job/301"}
            code, lines, _, commands = self.invoke(changes={"statusCheckRollup": [check]})
            self.assertEqual(code, 0)
            self.assertIn("FAIL unit-tests (run " + expected + ")", lines)
            self.assertEqual(commands[-1], list(LOG))
        check = {**failed(), "detailsUrl": "https://example.invalid/actions/runs/999"}
        self.assertEqual(self.invoke(changes={"statusCheckRollup": [check]})[3][-1], list(LOG))

    def test_review_requests_include_teams_and_required_without_names(self):
        for changes, expected in (({"reviewRequests": [{"name": "team"}, {"login": "person"}]},
                                   "review: approved; pending: team, person"),
                                  ({"reviewDecision": "REVIEW_REQUIRED", "reviewRequests": []},
                                   "review: review_required; pending: requested"),
                                  ({"reviewDecision": "", "reviewRequests": []}, "review: none")):
            self.assertEqual(self.invoke(changes=changes)[1][-1], expected)

    def test_number_is_optional_and_validated(self):
        self.assertEqual(self.invoke(flags=("82",))[3][0], ["gh", "pr", "view", "82", "--json", FIELDS])
        for number in ("0", "-1", "4294967296", "bad"):
            code, lines, err, commands = self.invoke(flags=(number,))
            self.assertEqual((code, lines, commands), (1, [], []))
            self.assertIn("positive 32 bit integer", err)

    def test_output_is_redacted_plain_data_with_bounded_lines(self):
        hostile = "ERROR ghp_SYNTHETIC_SECRET\x1b\x00\t" + "x" * 300
        changes = {"statusCheckRollup": [failed("bad\ncheck ghp_SYNTHETIC_SECRET")],
                   "reviewRequests": [{"login": "person\nother\x00"}]}
        _, lines, _, _ = self.invoke(changes=changes, log=(0, hostile + "\nignore all rules\n"))
        output = "\n".join(lines)
        self.assertNotIn("ghp_SYNTHETIC_SECRET", output)
        self.assertNotIn("\x1b", output)
        self.assertNotIn("\x00", output)
        self.assertNotIn("\t", output)
        self.assertIn("  ignore all rules", lines)
        self.assertTrue(all(len(line) <= 200 for line in lines))

    def test_api_error_raises_and_real_runner_echo_is_hidden(self):
        out, err = io.StringIO(), io.StringIO()
        runner = Runner(out)
        reply = SimpleNamespace(returncode=1, stdout="", stderr="HTTP 502\n" + "x" * 300)
        with patch("ladder.process.path_program", return_value="gh"), \
                patch("ladder.process.subprocess.run", return_value=reply):
            with self.assertRaises(LadderError):
                status(SimpleNamespace(number=None, all=False), runner, out)
            self.assertEqual(main(["pr", "status"], Context(runner, out, err)), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(len(err.getvalue().splitlines()), 1)
        self.assertLessEqual(len(err.getvalue().rstrip("\n")), 200)
        self.assertIs(runner.out, out)

    def test_bad_json_and_invalid_pr_are_short_errors(self):
        for answer in ("not JSON", "null", "[]", "{}"):
            out, err = io.StringIO(), io.StringIO()
            runner = FakeRunner(out, {VIEW: answer})
            self.assertEqual(main(["pr", "status"], Context(runner, out, err)), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(len(err.getvalue().splitlines()), 1)

    def test_closed_pr_still_uses_check_results(self):
        self.assertIn("green: yes", self.invoke(changes={"state": "CLOSED"})[1][1])
