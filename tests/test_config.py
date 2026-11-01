import unittest

from ladder.config import parse
from ladder.process import LadderError


class ParseTests(unittest.TestCase):
    def test_valid_file_has_2_tasks(self):
        config = parse('''
[tasks.test]
about = "Run tests"
run = "python -m unittest"
[tasks.release]
about = "Ship changes"
run = ["echo ready", "echo done"]
shell = "bash"
confirm = true
''', "ladder.toml")
        self.assertEqual(config.path, "ladder.toml")
        self.assertEqual(list(config.tasks), ["test", "release"])
        test = config.tasks["test"]
        self.assertEqual(test.name, "test")
        self.assertEqual(test.about, "Run tests")
        self.assertEqual(test.run, ("python -m unittest",))
        self.assertIsNone(test.shell)
        self.assertFalse(test.confirm)
        release = config.tasks["release"]
        self.assertEqual(release.name, "release")
        self.assertEqual(release.about, "Ship changes")
        self.assertEqual(release.run, ("echo ready", "echo done"))
        self.assertEqual(release.shell, "bash")
        self.assertTrue(release.confirm)
        self.assertEqual(config.gates, {})
        self.assertEqual(config.review, {})

    def assert_bad(self, text, message):
        with self.assertRaises(LadderError) as raised:
            parse(text, "ladder.toml")
        self.assertEqual(str(raised.exception), "ladder.toml: " + message)

    def test_bad_toml_names_file_and_reason(self):
        self.assert_bad("=", "not valid TOML: Invalid statement (at line 1, column 1)")

    def test_unknown_section_is_named(self):
        self.assert_bad("[other]", 'unknown section "other"')

    def test_tasks_must_be_a_table(self):
        self.assert_bad("tasks = []", 'task "tasks": must be a table of tables')

    def test_each_task_must_be_a_table(self):
        self.assert_bad('[tasks]\ntest = "echo hi"', 'task "test": must be a table')

    def test_about_is_required(self):
        self.assert_bad('[tasks.test]\nrun = "echo hi"',
                        'task "test": about must be a non empty string')

    def test_about_must_be_non_empty_text(self):
        for about in ('""', '"   "', "42"):
            with self.subTest(about=about):
                self.assert_bad('[tasks.test]\nabout = ' + about + '\nrun = "echo hi"',
                                'task "test": about must be a non empty string')

    def test_run_is_required(self):
        self.assert_bad('[tasks.test]\nabout = "Run tests"',
                        'task "test": run must be a non empty string or list of non empty strings')

    def test_run_must_be_non_empty_text_or_list(self):
        for run in ('""', '"   "', "[]", "42", '["echo hi", ""]', '["   "]', '[42]'):
            with self.subTest(run=run):
                self.assert_bad('[tasks.test]\nabout = "Run tests"\nrun = ' + run,
                                'task "test": run must be a non empty string or list of non empty strings')

    def test_shell_allows_only_bash(self):
        for shell in ('"sh"', "true"):
            with self.subTest(shell=shell):
                self.assert_bad('[tasks.test]\nabout = "Run tests"\nrun = "echo hi"\nshell = ' + shell,
                                'task "test": shell must be "bash"')

    def test_confirm_must_be_bool(self):
        for confirm in ('"true"', "1"):
            with self.subTest(confirm=confirm):
                self.assert_bad('[tasks.test]\nabout = "Run tests"\nrun = "echo hi"\nconfirm = ' + confirm,
                                'task "test": confirm must be a bool')

    def test_unknown_task_key_is_named(self):
        self.assert_bad('[tasks.test]\nabout = "Run tests"\nrun = "echo hi"\nextra = true',
                        'task "test": unknown key "extra"')

    def test_core_job_names_cannot_be_tasks(self):
        for name in ("help", "list", "doctor", "pr", "gates", "init", "install-skill"):
            with self.subTest(name=name):
                self.assert_bad(f'[tasks.{name}]\nabout = "Run tests"\nrun = "echo hi"',
                                f'task "{name}" clashes with the core job "{name}", rename it')

    def test_gates_and_review_are_kept_without_validation(self):
        config = parse('[gates]\nsteps = [1]\n[review]\nwait_for = "later"', "ladder.toml")
        self.assertEqual(config.gates, {"steps": [1]})
        self.assertEqual(config.review, {"wait_for": "later"})

    def test_missing_tasks_gives_empty_dict(self):
        config = parse("", "ladder.toml")
        self.assertEqual(config.tasks, {})
