
import copy
import json
import unittest
from unittest.mock import patch

from . import agent_questions as agent


class FrozenAnswersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = agent.load_contract()

    def answer_cases(self):
        questions = self.contract["questions"]
        for question_id in ("lab_gates", "lab_gates_agent_mode", "lab_longfail150"):
            source = questions.get(questions[question_id].get("same_as"), questions[question_id])
            yield question_id, None, source["answers"]
        for state_id, truth in questions["pr_states"]["states"].items():
            yield "pr_states", state_id, truth
        for task in questions["tasks_b5"]["tasks"]:
            yield "tasks_b5", task["id"], {"command": task["answer"]}

    def valid_runs(self, build_id):
        question_id = self.contract["builds"][build_id]["questions"]
        scores = {}
        for question, state, truth in self.answer_cases():
            if question == question_id:
                scores[state or question] = agent.score_answer(question, truth, state)
        run = {"answers": scores, "tool_calls": 6 if build_id == "B4" else 2,
               "piped_calls": 0, "false_green": False}
        if build_id == "B4":
            run["ladder_calls_by_state"] = {state: 1 for state in scores}
        return [copy.deepcopy(run) for _ in range(3)]

    def test_contract_reads_the_file_once_until_cache_clear(self):
        agent.load_contract.cache_clear()
        self.addCleanup(agent.load_contract.cache_clear)
        with patch.object(agent.Path, "read_text", return_value=json.dumps(self.contract)) as read:
            first = agent.load_contract()
            self.assertIs(agent.load_contract(), first)
            read.assert_called_once_with(encoding="utf-8")

    def test_contract_cache_clear_reads_modified_contract(self):
        original = agent.load_contract()
        changed = copy.deepcopy(original)
        changed["privacy"]["fake_secret_marker"] = "synthetic-replacement-marker"
        self.addCleanup(agent.load_contract.cache_clear)
        with patch.object(agent.Path, "read_text", return_value=json.dumps(changed)):
            self.assertIs(agent.load_contract(), original)
            agent.load_contract.cache_clear()
            self.assertEqual(agent.load_contract(), changed)

    def test_prompts_resolve_shared_question_and_tasks(self):
        questions = self.contract["questions"]
        for question_id in ("lab_gates", "lab_longfail150", "pr_states"):
            self.assertEqual(agent.build_prompt(question_id), questions[question_id]["prompt"])
        self.assertEqual(agent.build_prompt("lab_gates_agent_mode"), agent.build_prompt("lab_gates"))
        for task in questions["tasks_b5"]["tasks"]:
            prompt = agent.build_prompt("tasks_b5", task["id"])
            self.assertIn(task["text"], prompt)
            self.assertNotIn("<task text>", prompt)
        for task_id in (None, "missing"):
            with self.assertRaises(ValueError):
                agent.build_prompt("tasks_b5", task_id)
        with self.assertRaises(ValueError):
            agent.build_prompt("lab_gates", "check_before_commit")

    def test_last_nonempty_line_only(self):
        answer = {"green": "yes"}
        self.assertEqual(agent.parse_answer('notes\n{"green":"yes"}\n \n'), answer)
        for reply in (None, "", " \n", "[]", "null", "false", "2", '"text"',
                      '{"green":"yes"}\nDone', '```json\n{"green":"yes"}\n```',
                      '{\n"green":"yes"\n}', '{"green": }', '{"green": NaN}',
                      '{"green": Infinity}', '{"green": -Infinity}'):
            with self.subTest(reply=reply):
                self.assertIsNone(agent.parse_answer(reply))

    def test_marker_scrubbed_at_all_depths_and_in_keys(self):
        marker = self.contract["privacy"]["fake_secret_marker"]
        raw = {"before" + marker + "after": [marker, {"key": "x" + marker + "y"}],
               "safe": [True, 2, None]}
        parsed = agent.parse_answer(json.dumps(raw))
        self.assertNotIn(marker, json.dumps(parsed))
        self.assertEqual(parsed["safe"], [True, 2, None])
        self.assertIn("before[redacted]after", parsed)

    def test_normalisation_preserves_case_except_enum_values_and_types(self):
        cases = [("green", " YES  ", "yes"), ("green", "UnKnOwN", "unknown"),
                 ("review_pending", "NO", "no"), ("failed_check", " Unit-Tests ", "Unit-Tests"),
                 ("first_error_line", " ERROR   here ", "ERROR here"),
                 ("next_command", " ` $ ladder   gates ` ", "ladder gates"),
                 ("command", "`$ ladder gates`", "ladder gates"),
                 ("command", "$ `ladder gates`", "ladder gates"),
                 ("command", "```$ ladder pr   status```", "ladder pr status"),
                 ("failed_step", " 2 ", "2"), ("failed_step", 2, 2),
                 ("failed_step", True, True), ("command", None, None)]
        for key, value, expected in cases:
            with self.subTest(key=key, value=value):
                actual = agent.normalise(key, value)
                self.assertEqual(actual, expected)
                self.assertIs(type(actual), type(expected))

    def test_every_frozen_answer_and_each_wrong_or_missing_key(self):
        for question_id, state_id, truth in self.answer_cases():
            with self.subTest(question=question_id, state=state_id):
                self.assertEqual(agent.score_answer(question_id, truth, state_id),
                                 {key: True for key in truth})
                for key in truth:
                    wrong = dict(truth, **{key: "wrong"})
                    expected = {name: name != key for name in truth}
                    self.assertEqual(agent.score_answer(question_id, wrong, state_id), expected)
                    del wrong[key]
                    self.assertEqual(agent.score_answer(question_id, wrong, state_id), expected)
                self.assertEqual(agent.score_answer(question_id, None, state_id),
                                 {key: False for key in truth})

    def test_exact_gate_error_and_long_error_contains(self):
        truth = self.contract["questions"]["lab_gates"]["answers"]
        for question_id in ("lab_gates", "lab_gates_agent_mode"):
            for error, expected in ((" ERROR-lint-failed\t", True),
                                    ("prefix ERROR-lint-failed", False),
                                    ("error-lint-failed", False)):
                self.assertIs(agent.score_answer(question_id, dict(truth, first_error_line=error))
                              ["first_error_line"], expected)
            for step in ("2", 2.0, True, False, None):
                self.assertFalse(agent.score_answer(question_id, dict(truth, failed_step=step))["failed_step"])
        truth = self.contract["questions"]["lab_longfail150"]["answers"]
        self.assertTrue(agent.score_answer("lab_longfail150", dict(
            truth, first_error_line="prefix ERROR-synthetic-at-150 suffix"))["first_error_line"])
        self.assertFalse(agent.score_answer("lab_longfail150", dict(
            truth, first_error_line="ERROR-synthetic-at-15"))["first_error_line"])

    def test_false_green_for_all_states(self):
        states = {"pr-green": "yes", "pr-one-failed": "no",
                  "pr-review-pending": "yes", "pr-no-checks": "unknown",
                  "pr-log-missing": "no", "pr-api-error": "unknown"}
        cases = [("yes", {"green": "yes"}, False), ("yes", {"green": " YES "}, False),
                 ("yes", {"green": "no"}, False), ("yes", {"green": "unknown"}, False),
                 ("yes", {"green": None}, False), ("yes", {"green": True}, False),
                 ("yes", {}, False), ("yes", None, False),
                 ("no", {"green": "yes"}, True), ("no", {"green": " YES "}, True),
                 ("no", {"green": "no"}, False), ("no", {"green": "unknown"}, False),
                 ("no", {"green": None}, False), ("no", {"green": True}, False),
                 ("no", {}, False), ("no", None, False),
                 ("unknown", {"green": "yes"}, True), ("unknown", {"green": " YES "}, True),
                 ("unknown", {"green": "no"}, False), ("unknown", {"green": "unknown"}, False),
                 ("unknown", {"green": None}, False), ("unknown", {"green": True}, False),
                 ("unknown", {}, False), ("unknown", None, False)]
        self.assertEqual(set(states), set(self.contract["questions"]["pr_states"]["states"]))
        for state_id, state_truth in states.items():
            self.assertEqual(self.contract["questions"]["pr_states"]["states"][state_id]["green"], state_truth)
            for truth, answer, expected in cases:
                if truth == state_truth:
                    with self.subTest(state=state_id, answer=answer):
                        self.assertIs(agent.is_false_green(state_id, answer), expected)

    def test_piped_call_table(self):
        cases = {"ladder gates | head -10": 1,
                 "ladder gates 2>&1 | tail -15": 1,
                 "ladder gates *>&1 | Select-Object -Last 20": 1,
                 "ladder gates | grep ERROR": 1,
                 "ladder gates | sed -n 1p": 1,
                 "ladder gates | Select-String ERROR": 1,
                 "ladder gates | Select -First 10": 1,
                 "ladder gates | cat | tail -2": 1,
                 "& .\\ladder.exe gates | tail -2 | head -1": 1,
                 "ladder gates | tail -2; ladder gates | head -2": 1,
                 "git log | head -2": 0,
                 "echo ladder | tail -2": 0,
                 'echo "ladder gates | tail -2"': 0,
                 'ladder run "argument | head -2"': 0,
                 "ladder gates; git log | head -2": 0,
                 "ladder gates && git log | head -2": 0,
                 "ladder gates || git log | head -2": 0,
                 "ladder gates | head0": 0,
                 "ladder gates | Select -Last 2": 0,
                 "ladder gates": 0}
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(agent.count_piped_calls([command]), expected)
        self.assertEqual(agent.count_piped_calls(list(cases)), sum(cases.values()))
        self.assertEqual(agent.count_piped_calls([]), 0)

    def test_run_passes_with_complete_true_scores(self):
        scores = self.valid_runs("B1")[0]["answers"]
        self.assertTrue(agent.run_passes(scores))

    def test_run_rejects_missing_scores(self):
        for invalid in ({}, None, [], {"missing": {"value": True}},
                        {"lab_gates": {}}, {"lab_gates": {"gates_passed": True}}):
            with self.subTest(scores=invalid):
                self.assertFalse(agent.run_passes(invalid))

    def test_run_rejects_false_success_flags(self):
        scores = self.valid_runs("B1")[0]["answers"]
        for flag in (True, None, 0, 1, "false"):
            with self.subTest(flag=flag):
                self.assertFalse(agent.run_passes(scores, false_green=flag))
                self.assertFalse(agent.run_passes(scores, false_success=flag))

    def test_run_rejects_wrong_or_non_boolean_scores(self):
        scores = self.valid_runs("B1")[0]["answers"]
        for value in (False, 1, "true", None):
            with self.subTest(value=value):
                changed = copy.deepcopy(scores)
                changed["lab_gates"]["gates_passed"] = value
                self.assertFalse(agent.run_passes(changed))

    def test_every_build_passes_with_complete_answers(self):
        for build_id in ("B1", "B2", "B3a_B3b", "B4", "B5"):
            runs = self.valid_runs(build_id)
            self.assertTrue(agent.arm_verdict(build_id, runs))
            self.assertTrue(agent.arm_verdict({"id": build_id}, runs))
            self.assertTrue(agent.arm_verdict(self.contract["builds"][build_id], runs))

    def test_every_build_rejects_each_wrong_answer(self):
        for build_id in ("B1", "B2", "B3a_B3b", "B4", "B5"):
            runs = self.valid_runs(build_id)
            for run_index in range(3):
                for question_id, scores in runs[run_index]["answers"].items():
                    for key in scores:
                        with self.subTest(build=build_id, run=run_index, question=question_id, key=key):
                            changed = copy.deepcopy(runs)
                            changed[run_index]["answers"][question_id][key] = False
                            self.assertFalse(agent.arm_verdict(build_id, changed))

    def test_every_build_rejects_each_missing_answer(self):
        for build_id in ("B1", "B2", "B3a_B3b", "B4", "B5"):
            runs = self.valid_runs(build_id)
            for run_index in range(3):
                for question_id, scores in runs[run_index]["answers"].items():
                    for key in scores:
                        with self.subTest(build=build_id, run=run_index, question=question_id, key=key):
                            changed = copy.deepcopy(runs)
                            del changed[run_index]["answers"][question_id][key]
                            self.assertFalse(agent.arm_verdict(build_id, changed))

    def test_every_build_rejects_false_success_flags(self):
        for build_id in ("B1", "B2", "B3a_B3b", "B4", "B5"):
            runs = self.valid_runs(build_id)
            for run_index in range(3):
                for flag in ("false_green", "false_success"):
                    with self.subTest(build=build_id, run=run_index, flag=flag):
                        changed = copy.deepcopy(runs)
                        changed[run_index][flag] = True
                        self.assertFalse(agent.arm_verdict(build_id, changed))

    def test_build_specific_call_rules_and_no_extra_caps(self):
        for build_id in ("B1", "B2", "B5"):
            runs = self.valid_runs(build_id)
            runs[0].update(tool_calls=100, piped_calls=10)
            self.assertTrue(agent.arm_verdict(build_id, runs))
        for calls, pipes, expected in ((0, 0, True), (2, 0, True), (3, 0, False), (2, 1, False)):
            runs = self.valid_runs("B3a_B3b")
            runs[0].update(tool_calls=calls, piped_calls=pipes)
            self.assertIs(agent.arm_verdict("B3a_B3b", runs), expected)

    def test_b4_requires_one_ladder_call_for_each_state(self):
        runs = self.valid_runs("B4")
        for run_index in range(3):
            for state_id in runs[run_index]["ladder_calls_by_state"]:
                for count in (0, 2, True, "1", 1.0, None):
                    with self.subTest(run=run_index, state=state_id, count=count):
                        changed = copy.deepcopy(runs)
                        changed[run_index]["ladder_calls_by_state"][state_id] = count
                        self.assertFalse(agent.arm_verdict("B4", changed))

    def test_b4_requires_the_exact_state_call_mapping(self):
        runs = self.valid_runs("B4")
        counts = runs[0]["ladder_calls_by_state"]
        for invalid in (None, [], {}, {key: value for key, value in counts.items() if key != "pr-green"},
                        dict(counts, unexpected=1)):
            with self.subTest(counts=invalid):
                changed = copy.deepcopy(runs)
                changed[0]["ladder_calls_by_state"] = invalid
                self.assertFalse(agent.arm_verdict("B4", changed))
        del runs[0]["ladder_calls_by_state"]
        self.assertFalse(agent.arm_verdict("B4", runs))

    def test_b4_total_tool_calls_does_not_prove_one_call_per_state(self):
        runs = self.valid_runs("B4")
        runs[0]["ladder_calls_by_state"].update({"pr-green": 2, "pr-one-failed": 0})
        self.assertEqual(runs[0]["tool_calls"], 6)
        self.assertFalse(agent.arm_verdict("B4", runs))
        runs = self.valid_runs("B4")
        runs[0]["tool_calls"] = 100
        self.assertTrue(agent.arm_verdict("B4", runs))

    def test_malformed_runs_fail_closed(self):
        for build_id in ("B1", "B2", "B3a_B3b", "B4", "B5"):
            runs = self.valid_runs(build_id)
            for invalid in (None, {}, [], runs[:2], runs + runs[:1], [None] * 3):
                self.assertFalse(agent.arm_verdict(build_id, invalid))
            for field in ("answers", "tool_calls", "piped_calls", "false_green"):
                changed = copy.deepcopy(runs)
                del changed[0][field]
                self.assertFalse(agent.arm_verdict(build_id, changed))
            for field in ("tool_calls", "piped_calls"):
                for value in (-1, True, "2", 2.0, None):
                    changed = copy.deepcopy(runs)
                    changed[0][field] = value
                    self.assertFalse(agent.arm_verdict(build_id, changed))
            changed = copy.deepcopy(runs)
            del changed[0]["answers"][next(iter(changed[0]["answers"]))]
            self.assertFalse(agent.arm_verdict(build_id, changed))
            for flag in ("false_green", "false_success"):
                for value in (0, None, "false"):
                    changed = copy.deepcopy(runs)
                    changed[0][flag] = value
                    self.assertFalse(agent.arm_verdict(build_id, changed))

    def test_sessions_count_prompts_not_answer_keys(self):
        runs = self.contract["agent_run"]["runs_per_question_per_arm"]
        for build_id, build in self.contract["builds"].items():
            if build_id == "B6b":
                continue
            question = self.contract["questions"][build["questions"]]
            prompts = len(question["states"]) if "states" in question else len(question.get("tasks", [None]))
            with self.subTest(build=build_id):
                self.assertEqual(agent.session_plan(build_id), prompts * runs)
                self.assertEqual(agent.session_plan(build), prompts * runs)

    def test_b6b_has_no_session_count(self):
        self.assertIsNone(agent.session_plan("B6b"))

    def test_b6b_has_no_pass_verdict(self):
        self.assertIsNone(agent.arm_verdict("B6b", []))

    def test_unknown_build_has_no_session_plan(self):
        with self.assertRaises(ValueError):
            agent.session_plan("missing")


if __name__ == "__main__":
    unittest.main()
