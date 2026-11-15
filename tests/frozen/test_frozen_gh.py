"""Check the local gh stub and the six frozen PR states."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
FAKE = HERE / "fake_gh.py"
CONTRACT = json.loads((HERE / "contracts.json").read_text(encoding="utf-8"))
TRUTH = CONTRACT["questions"]["pr_states"]["states"]
CHECK_RESULTS = {
    "pr-green": ["SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS"],
    "pr-one-failed": ["FAILURE", "SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS"],
    "pr-review-pending": ["SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS"],
    "pr-no-checks": [],
    "pr-log-missing": ["SUCCESS", "FAILURE", "SUCCESS", "SUCCESS", "SUCCESS"],
}
CHECK_NAMES = ["unit-tests", "lint", "synthetic-build", "synthetic-types",
               "synthetic-format"]


class FrozenGhTests(unittest.TestCase):
    def invoke(self, state, *args):
        env = dict(os.environ, FAKE_GH_STATE=str(state), PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, str(FAKE), *args], env=env,
                              text=True, capture_output=True, timeout=5)

    def run_state(self, state_id, *args):
        return self.invoke(HERE / "pr_states" / (state_id + ".json"), *args)

    def saved_state(self, state_id):
        return json.loads((HERE / "pr_states" / (state_id + ".json"))
                          .read_text(encoding="utf-8"))

    def stub(self, state_id, prefix):
        return next(call for call in self.saved_state(state_id)["calls"]
                    if call["match"] == prefix)

    def payload(self, state_id, prefix):
        return json.loads(self.stub(state_id, prefix)["stdout"])

    def write_state(self, folder, calls):
        path = Path(folder) / "state.json"
        path.write_text(json.dumps({"id": "synthetic-test", "calls": calls}),
                        encoding="utf-8")
        return path

    def test_state_ids_and_exact_schema(self):
        paths = list((HERE / "pr_states").glob("*.json"))
        self.assertEqual({path.stem for path in paths}, set(TRUTH))
        for path in paths:
            state = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(state), {"id", "calls"})
            self.assertEqual(state["id"], path.stem)
            for call in state["calls"]:
                self.assertEqual(set(call), {"match", "exit", "stdout", "stderr"})
                self.assertIsInstance(call["match"], list)
                self.assertTrue(all(isinstance(arg, str) for arg in call["match"]))
                self.assertIs(type(call["exit"]), int)
                self.assertIsInstance(call["stdout"], str)
                self.assertIsInstance(call["stderr"], str)

    def test_saved_states_do_not_contain_the_secret_marker(self):
        marker = CONTRACT["privacy"]["fake_secret_marker"]
        for path in (HERE / "pr_states").glob("*.json"):
            with self.subTest(state=path.stem):
                self.assertNotIn(marker, path.read_text(encoding="utf-8"))

    def test_longest_prefix_wins(self):
        calls = [{"match": match, "exit": code, "stdout": output, "stderr": ""}
                 for match, code, output in [(["pr"], 1, "short"),
                                             (["pr", "view"], 0, "long"),
                                             (["pr", "view", "101"], 3, "longest")]]
        with tempfile.TemporaryDirectory() as folder:
            path = self.write_state(folder, calls)
            reply = self.invoke(path, "pr", "view", "101", "--json", "number")
            self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                             (3, "longest", ""))

    def test_no_match_is_an_error_and_names_only_first_three_args(self):
        reply = self.run_state("pr-green", "issue", "view", "101", "synthetic-extra")
        self.assertEqual(reply.returncode, 1)
        self.assertEqual(reply.stdout, "")
        self.assertEqual(reply.stderr, "fake gh: no stub for issue view 101\n")

    def test_special_commands(self):
        reply = self.run_state("pr-green", "--version")
        self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                         (0, "gh version 0.0.0 (fake)\n", ""))
        reply = self.run_state("pr-green", "auth", "status")
        self.assertEqual((reply.returncode, reply.stdout, reply.stderr), (0, "", ""))

    def test_json_field_lists_do_not_filter_the_reply(self):
        plain = self.run_state("pr-green", "pr", "view")
        for fields in ("number", "url,state", "synthetic-unused-field"):
            reply = self.run_state("pr-green", "pr", "view", "--json", fields)
            self.assertEqual((reply.returncode, reply.stdout), (0, plain.stdout))

    def test_jq_flags_are_rejected_anywhere(self):
        for args in (("--jq", ".", "pr", "view"), ("pr", "--jq=.", "view"),
                     ("pr", "view", "-q", "."), ("pr", "view", "-q=."),
                     ("pr", "view", "-q.name"), ("pr", "view", "--jq=.name")):
            with self.subTest(args=args):
                reply = self.run_state("pr-green", *args)
                self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                                 (2, "", "fake gh: --jq not supported; read the JSON yourself\n"))

    def test_invalid_state_fails_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            cases = ["{", "{}", '{"id":"synthetic","calls":{}}',
                     '{"id":"synthetic","calls":[{"match":[]}]}']
            for content in cases:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    reply = self.invoke(path, "pr", "view")
                    self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                                     (1, "", "fake gh: invalid FAKE_GH_STATE\n"))
            reply = self.invoke(Path(folder) / "absent.json", "pr", "view")
            self.assertEqual(reply.returncode, 1)
            self.assertNotIn("Traceback", reply.stderr)

    def test_normal_states_have_expected_checks(self):
        for state_id, results in CHECK_RESULTS.items():
            with self.subTest(state=state_id):
                pr = self.payload(state_id, ["pr", "view"])
                checks = self.payload(state_id, ["pr", "checks"])
                self.assertEqual((pr["number"], pr["state"], pr["headRefName"]),
                                 (101, "OPEN", "synthetic-branch"))
                self.assertEqual(pr["url"], "https://example.invalid/synthetic/pull/101")
                self.assertEqual([check["name"] for check in checks],
                                 [] if state_id == "pr-no-checks" else CHECK_NAMES)
                self.assertEqual([check["state"] for check in checks], results)
                self.assertEqual([check["conclusion"] for check in pr["statusCheckRollup"]],
                                 results)
                buckets = {
                    "pr-green": ["pass", "pass", "pass", "pass", "pass"],
                    "pr-one-failed": ["fail", "pass", "pass", "pass", "pass"],
                    "pr-review-pending": ["pass", "pass", "pass", "pass", "pass"],
                    "pr-no-checks": [],
                    "pr-log-missing": ["pass", "fail", "pass", "pass", "pass"],
                }
                self.assertEqual([check["bucket"] for check in checks], buckets[state_id])

    def test_normal_states_have_expected_reviews(self):
        cases = [("pr-green", "APPROVED", [], []),
                 ("pr-one-failed", "APPROVED", [], []),
                 ("pr-review-pending", "REVIEW_REQUIRED",
                  [{"__typename": "User", "login": "synthetic-reviewer"}], [False]),
                 ("pr-no-checks", "APPROVED", [], []),
                 ("pr-log-missing", "APPROVED", [], [])]
        for state_id, decision, requests, resolved in cases:
            with self.subTest(state=state_id):
                pr = self.payload(state_id, ["pr", "view"])
                self.assertEqual(pr["reviewDecision"], decision)
                self.assertEqual(pr["reviewRequests"],
                                 requests)
                if state_id == "pr-review-pending":
                    self.assertEqual(pr["latestReviews"], [])
                graph = self.payload(state_id, ["api", "graphql"])
                nodes = graph["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
                self.assertEqual([node["isResolved"] for node in nodes], resolved)
                for node in nodes:
                    self.assertEqual(set(node), {"isResolved", "isOutdated", "path", "line", "comments"})
                    self.assertEqual(set(node["comments"]["nodes"][0]), {"author", "body", "url"})

    def test_normal_states_have_expected_run_jobs(self):
        cases = [("pr-green", "success", ["success"] * 5),
                 ("pr-one-failed", "failure", ["failure", "success", "success", "success", "success"]),
                 ("pr-review-pending", "success", ["success"] * 5),
                 ("pr-no-checks", "success", []),
                 ("pr-log-missing", "failure", ["success", "failure", "success", "success", "success"])]
        for state_id, conclusion, jobs in cases:
            with self.subTest(state=state_id):
                run = self.payload(state_id, ["run", "view"])
                self.assertEqual(self.payload(state_id, ["run", "list"]), [run])
                self.assertEqual(run["conclusion"], conclusion)
                self.assertEqual([job["name"] for job in run["jobs"]],
                                 [] if state_id == "pr-no-checks" else CHECK_NAMES)
                self.assertEqual([job["conclusion"] for job in run["jobs"]], jobs)

    def test_fixture_commands_return_saved_responses(self):
        for state_id in TRUTH:
            if state_id == "pr-api-error":
                continue
            for args in (("pr", "view"), ("pr", "checks"), ("api", "graphql"),
                         ("run", "view"), ("run", "list")):
                with self.subTest(state=state_id, args=args):
                    reply = self.run_state(state_id, *args)
                    call = self.stub(state_id, list(args))
                    self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                                     (call["exit"], call["stdout"], call["stderr"]))

    def test_no_checks_error_is_exact(self):
        reply = self.run_state("pr-no-checks", "pr", "checks", "--json", "name,state")
        self.assertEqual((reply.returncode, json.loads(reply.stdout), reply.stderr),
                         (1, [], "no checks reported on the 'synthetic-branch' branch\n"))

    def test_failed_log_has_exact_count_and_error_location(self):
        for args in (("run", "view", "--log-failed", "201"),
                     ("run", "view", "201", "--log-failed")):
            reply = self.run_state("pr-one-failed", *args)
            lines = reply.stdout.splitlines()
            self.assertEqual((reply.returncode, len(lines), reply.stderr), (0, 200, ""))
            self.assertEqual(lines[2], TRUTH["pr-one-failed"]["first_error_line"])
            self.assertEqual(sum("ERROR-" in line for line in lines), 1)

    def test_missing_log_returns_the_exact_error(self):
        for args in (("run", "view", "--log-failed", "201"),
                     ("run", "view", "201", "--log-failed")):
            with self.subTest(args=args):
                missing = self.run_state("pr-log-missing", *args)
                self.assertEqual((missing.returncode, missing.stdout, missing.stderr),
                                 (1, "", "log not found\n"))

    def test_api_error_covers_every_command(self):
        state = self.saved_state("pr-api-error")
        self.assertTrue(any(call["match"] == [] for call in state["calls"]))
        for call in state["calls"]:
            with self.subTest(match=call["match"]):
                self.assertEqual((call["exit"], call["stdout"], call["stderr"]),
                                 (1, "", "HTTP 502: Bad Gateway\n"))
                reply = self.run_state("pr-api-error", *call["match"])
                self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                                 (1, "", "HTTP 502: Bad Gateway\n"))
        for args in (("--version",), ("auth", "status"), ("pr", "view"),
                     ("synthetic-unknown",)):
            with self.subTest(args=args):
                reply = self.run_state("pr-api-error", *args)
                self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                                 (1, "", "HTTP 502: Bad Gateway\n"))
        for args in (("pr", "view", "--jq", "."), ("synthetic-unknown", "-q=."),
                     ("synthetic-unknown", "-q.name"), ("pr", "view", "--jq=.name")):
            with self.subTest(args=args):
                reply = self.run_state("pr-api-error", *args)
                self.assertEqual((reply.returncode, reply.stdout, reply.stderr),
                                 (2, "", "fake gh: --jq not supported; read the JSON yourself\n"))

    def test_child_secret_is_scrubbed_from_parsed_answer_scores_and_verdict(self):
        from . import agent_questions

        marker = CONTRACT["privacy"]["fake_secret_marker"]
        with tempfile.TemporaryDirectory() as folder:
            state = self.saved_state("pr-one-failed")
            call = next(call for call in state["calls"]
                        if call["match"] == ["run", "view", "201", "--log-failed"])
            lines = call["stdout"].splitlines()
            lines[9] = marker
            call["stdout"] = "\n".join(lines) + "\n"
            path = Path(folder) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            reply = self.invoke(path, "run", "view", "201", "--log-failed")
            self.assertIn(marker, reply.stdout)
            text = json.dumps({"first_error_line": reply.stdout.strip()})
            parsed = agent_questions.parse_answer(text)
            score = agent_questions.score_answer("pr_states", parsed, state_id="pr-one-failed")
            verdict = agent_questions.arm_verdict("B4", [{"answers": {"pr-one-failed": score},
                                                          "tool_calls": 1, "piped_calls": 0,
                                                          "false_green": False}])
            self.assertNotIn(marker, json.dumps([parsed, score, verdict]))


if __name__ == "__main__":
    unittest.main()
