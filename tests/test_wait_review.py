import io
import json
import unittest

from ladder.cli import Context, main
from ladder.config import parse
from ladder.process import LadderError
from tests.test_cli import FakeRunner


HEAD = "abcdef0123456789" * 2 + "abcdef01"
NEW_HEAD = "1234567890abcdef" * 2 + "12345678"
HEAD_COMMAND = ("gh", "pr", "view", "82", "--json", "headRefOid", "-q", ".headRefOid")
REVIEWS_COMMAND = ("gh", "api", "repos/{owner}/{repo}/pulls/82/reviews", "--paginate")


def review(login="bot", commit=HEAD, state="APPROVED"):
    return {"user": {"login": login}, "commit_id": commit, "state": state}


class FakeTime:
    def __init__(self):
        self.now = 1000
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class WaitReviewTests(unittest.TestCase):
    def invoke(self, polls=(), *, config='[review]\nwait_for = ["bot"]', flags=()):
        out, err = io.StringIO(), io.StringIO()
        answers = {HEAD_COMMAND: [head for head, _ in polls],
                   REVIEWS_COMMAND: [reviews for _, reviews in polls]}
        runner = FakeRunner(out, answers)
        timer = FakeTime()
        project = None if config is None else parse(config, "ladder.toml")
        code = main(["pr", "wait-review", "82", *flags],
                    Context(runner, out, err, load_config=lambda _: project,
                            clock=timer.clock, sleep=timer.sleep))
        lines = [line for line in out.getvalue().splitlines() if not line.startswith("$ ")]
        return code, lines, err.getvalue(), runner.commands, timer.sleeps

    def test_no_reviewer_stops_without_commands_or_sleep(self):
        # Cases: no file, no section, no key, explicitly empty list.
        for config in (None, "", "[review]", "[review]\nwait_for = []"):
            with self.subTest(config=config):
                self.assertEqual(self.invoke(config=config),
                                 (1, [], 'ladder: no reviewer set: add [review] wait_for = ["login"] '
                                  'to ladder.toml or pass --bot\n', [], []))

    def test_single_reviewer_done_at_once_for_each_finished_state(self):
        for state in ("APPROVED", "COMMENTED", "CHANGES_REQUESTED", "DISMISSED"):
            with self.subTest(state=state):
                self.assertEqual(self.invoke([(HEAD + "\n", json.dumps([review(state=state)]))]),
                                 (0, [f"abcdef0: done: bot ({state})"], "",
                                  [list(HEAD_COMMAND), list(REVIEWS_COMMAND)], []))

    def test_second_reviewer_finishes_on_second_poll(self):
        first = [review()]
        second = [*first, review("person", state="COMMENTED")]
        code, lines, err, commands, sleeps = self.invoke(
            [(HEAD, json.dumps(first)), (HEAD, json.dumps(second))],
            config='[review]\nwait_for = ["bot", "person"]')
        self.assertEqual((code, err, sleeps), (0, "", [30]))
        self.assertEqual(lines, ["abcdef0: waiting for person",
                                 "abcdef0: done: bot (APPROVED), person (COMMENTED)"])
        self.assertEqual(commands, [list(HEAD_COMMAND), list(REVIEWS_COMMAND)] * 2)

    def test_old_commit_and_pending_reviews_do_not_finish_the_wait(self):
        for unfinished in (review(commit=NEW_HEAD), review(state="PENDING"),
                           review("someone-else")):
            with self.subTest(unfinished=unfinished):
                code, lines, err, _, sleeps = self.invoke(
                    [(HEAD, json.dumps([unfinished])), (HEAD, json.dumps([review()]))])
                self.assertEqual((code, err, sleeps), (0, "", [30]))
                self.assertEqual(lines, ["abcdef0: waiting for bot",
                                         "abcdef0: done: bot (APPROVED)"])

    def test_new_head_requires_fresh_reviews_from_every_reviewer(self):
        first = [review()]
        stale = [*first, review("person")]
        fresh = [*stale, review(commit=NEW_HEAD), review("person", NEW_HEAD, "COMMENTED")]
        code, lines, err, _, sleeps = self.invoke(
            [(HEAD, json.dumps(first)), (NEW_HEAD, json.dumps(stale)),
             (NEW_HEAD, json.dumps(fresh))],
            config='[review]\nwait_for = ["bot", "person"]')
        self.assertEqual((code, err, sleeps), (0, "", [30, 30]))
        self.assertEqual(lines, ["abcdef0: waiting for person",
                                 "head changed: abcdef0 -> 1234567",
                                 "1234567: waiting for bot, person",
                                 "1234567: done: bot (APPROVED), person (COMMENTED)"])

    def test_timeout_uses_latest_head_and_does_not_repeat_unchanged_status(self):
        code, lines, err, commands, sleeps = self.invoke(
            [(HEAD, "[]"), (NEW_HEAD, "[]"), (NEW_HEAD, "[]")],
            flags=("--timeout-mins", "1"), config='[review]\nwait_for = ["bot", "person"]')
        self.assertEqual((code, sleeps), (1, [30, 30]))
        self.assertEqual(lines, ["abcdef0: waiting for bot, person",
                                 "head changed: abcdef0 -> 1234567",
                                 "1234567: waiting for bot, person"])
        self.assertEqual(err, "ladder: timed out after 1 min; still waiting for bot, person on 1234567\n")
        self.assertEqual(commands, [list(HEAD_COMMAND), list(REVIEWS_COMMAND)] * 3)

    def test_default_timeout_is_20_minutes(self):
        code, lines, err, _, sleeps = self.invoke([(HEAD, "[]")] * 41)
        self.assertEqual((code, lines, sleeps), (1, ["abcdef0: waiting for bot"], [30] * 40))
        self.assertEqual(err, "ladder: timed out after 20 min; still waiting for bot on abcdef0\n")

    def test_repeated_bot_flags_replace_config_or_work_without_a_file(self):
        for config in (None, '[review]\nwait_for = ["other"]'):
            with self.subTest(config=config):
                code, lines, err, _, sleeps = self.invoke(
                    [(HEAD, json.dumps([review("human"), review("second")]))],
                    config=config, flags=("--bot", "human", "--bot", "second"))
                self.assertEqual((code, err, sleeps), (0, "", []))
                self.assertEqual(lines, ["abcdef0: done: human (APPROVED), second (APPROVED)"])

    def test_login_matching_ignores_case_and_duplicates_keep_first_spelling(self):
        code, lines, err, _, sleeps = self.invoke(
            [(HEAD, json.dumps([review("bOt")]))],
            config='[review]\nwait_for = [" Bot ", "BOT"]')
        self.assertEqual((code, lines, err, sleeps),
                         (0, ["abcdef0: done: Bot (APPROVED)"], "", []))

    def test_concatenated_pages_include_every_reviewer(self):
        for separator in ("", "\n \t"):
            with self.subTest(separator=separator):
                answer = json.dumps([review()]) + separator + json.dumps([review("person")])
                code, lines, err, _, sleeps = self.invoke(
                    [(HEAD, " \n" + answer + "\n")],
                    config='[review]\nwait_for = ["bot", "person"]')
                self.assertEqual((code, err, sleeps), (0, "", []))
                self.assertEqual(lines, ["abcdef0: done: bot (APPROVED), person (APPROVED)"])

    def test_last_finished_review_on_head_wins_and_pending_does_not_erase_it(self):
        answer = [review(), review(state="CHANGES_REQUESTED"), review(state="PENDING")]
        code, lines, err, _, sleeps = self.invoke([(HEAD, json.dumps(answer))])
        self.assertEqual((code, lines, err, sleeps),
                         (0, ["abcdef0: done: bot (CHANGES_REQUESTED)"], "", []))

    def test_bad_json_and_missing_or_invalid_fields_fail_without_sleep(self):
        # Cases: empty, invalid syntax, bad later page, wrong container, bad row or field.
        cases = [("", "bad JSON"), ("bad", "bad JSON"), ("[]oops", "bad JSON"),
                 ('{}', "array"), ('[null]', "user.login"), ('[{}]', "user.login")]
        for field in ("user", "commit_id", "state"):
            broken = review()
            del broken[field]
            cases.append((json.dumps([broken]), "user.login" if field == "user" else field))
        for field in ("commit_id", "state"):
            for invalid in (None, 42, "", "  "):
                cases.append((json.dumps([{**review(), field: invalid}]), field))
        for invalid in (None, {}, {"login": 42}, {"login": ""}):
            cases.append((json.dumps([{**review(), "user": invalid}]), "user.login"))
        for answer, message in cases:
            with self.subTest(answer=answer):
                code, lines, err, commands, sleeps = self.invoke([(HEAD, answer)])
                self.assertEqual((code, lines, sleeps), (1, [], []))
                self.assertIn(message, err)
                self.assertTrue(err.startswith("ladder: gh returned "))
                self.assertEqual(len(err.splitlines()), 1)
                self.assertEqual(commands, [list(HEAD_COMMAND), list(REVIEWS_COMMAND)])

    def test_command_failure_stops_immediately(self):
        for head, answer, count in ((LadderError("gh: exit 1: missing PR"), "[]", 1),
                                    (HEAD, LadderError("gh: exit 1: denied"), 2)):
            with self.subTest(count=count):
                code, lines, err, commands, sleeps = self.invoke([(head, answer)])
                self.assertEqual((code, lines, sleeps), (1, [], []))
                self.assertIn("ladder: gh: exit 1:", err)
                self.assertEqual(len(commands), count)

    def test_empty_or_invalid_head_is_a_plain_error_before_reviews(self):
        for head in ("", " \n", "not a sha"):
            with self.subTest(head=head):
                code, lines, err, commands, sleeps = self.invoke([(head, "[]")])
                self.assertEqual((code, lines, sleeps), (1, [], []))
                self.assertIn("head commit", err)
                self.assertEqual(commands, [list(HEAD_COMMAND)])

    def test_timeout_and_bot_arguments_are_validated_before_commands(self):
        # Cases: minimum, zero, negative, fractional, non numeric, blank and overflow text.
        for setting in ("0", "-1", "1.5", "no", "", "9" * 5000):
            with self.subTest(setting=setting):
                code, lines, err, commands, sleeps = self.invoke(flags=("--timeout-mins", setting))
                self.assertEqual((code, lines, commands, sleeps), (1, [], [], []))
                self.assertIn("--timeout-mins", err)
                self.assertIn("whole number", err)
        for login in ("", "  "):
            with self.subTest(login=login):
                code, lines, err, commands, sleeps = self.invoke(flags=("--bot", login))
                self.assertEqual((code, lines, commands, sleeps), (1, [], [], []))
                self.assertIn("--bot", err)
                self.assertIn("non empty", err)

    def test_help_needs_no_config_commands_or_sleep(self):
        code, lines, err, commands, sleeps = self.invoke(config=None, flags=("--help",))
        self.assertEqual((code, err, commands, sleeps), (0, "", [], []))
        self.assertIn("--bot", "\n".join(lines))
        self.assertIn("--timeout-mins", "\n".join(lines))
