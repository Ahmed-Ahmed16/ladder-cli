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

    def test_invalid_file_structure_and_keys_report_exact_errors(self):
        cases = [
            ("=", "not valid TOML: Invalid statement (at line 1, column 1)"),
            ("[other]", 'unknown section "other"'),
            ("tasks = []", 'task "tasks": must be a table of tables'),
            ('[tasks]\ntest = "echo hi"', 'task "test": must be a table'),
            ('[tasks.test]\nabout = "Run tests"\nrun = "echo hi"\nextra = true',
             'task "test": unknown key "extra"'),
            ('[review]\nwait_for = []\nbot = "person"', 'review: unknown key "bot"'),
            ('gates = []', 'gates: must be a table'),
        ]
        for text, message in cases:
            with self.subTest(text=text):
                self.assert_bad(text, message)

    def test_about_must_be_non_empty_text(self):
        for about in (None, '""', '"   "', "42"):
            with self.subTest(about=about):
                text = ('[tasks.test]\nrun = "echo hi"' if about is None else
                        '[tasks.test]\nabout = ' + about + '\nrun = "echo hi"')
                self.assert_bad(text,
                                'task "test": about must be a non empty string')

    def test_run_must_be_non_empty_text_or_list(self):
        for run in (None, '""', '"   "', "[]", "42", '["echo hi", ""]', '["   "]', '[42]'):
            with self.subTest(run=run):
                text = '[tasks.test]\nabout = "Run tests"' + ('\nrun = ' + run if run is not None else '')
                self.assert_bad(text,
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

    def test_core_job_names_cannot_be_tasks(self):
        for name in ("help", "list", "doctor", "pr", "gates", "add", "init", "install-skill"):
            with self.subTest(name=name):
                self.assert_bad(f'[tasks.{name}]\nabout = "Run tests"\nrun = "echo hi"',
                                f'task "{name}" clashes with the core job "{name}", rename it')

    def test_gates_and_review_are_exposed(self):
        config = parse('[gates]\nrun = "check"\n[review]\nwait_for = ["reviewer"]', "ladder.toml")
        self.assertEqual(config.gates, {"run": ("check",)})
        self.assertEqual(config.review, {"wait_for": ["reviewer"]})

    def test_review_allows_missing_empty_and_multiple_logins(self):
        # Cases: missing table, missing key, empty list, 1 login, several logins.
        for text, expected in (("", {}), ("[review]", {}),
                               ('[review]\nwait_for = []', {"wait_for": []}),
                               ('[review]\nwait_for = ["Bot", "person"]',
                                {"wait_for": ["Bot", "person"]})):
            with self.subTest(text=text):
                self.assertEqual(parse(text, "ladder.toml").review, expected)

    def test_review_must_be_a_table(self):
        for setting in ('[]', 'true', '"reviewer"'):
            with self.subTest(setting=setting):
                self.assert_bad('review = ' + setting, 'review: must be a table')

    def test_review_wait_for_must_be_a_list_of_non_empty_strings(self):
        # Cases: scalar, wrong member type, empty member, whitespace member, nested list.
        for setting in ('"reviewer"', '42', 'true', '{}', '[42]', '[false]',
                        '[""]', '["  "]', '["reviewer", ""]', '[["reviewer"]]'):
            with self.subTest(setting=setting):
                self.assert_bad('[review]\nwait_for = ' + setting,
                                'review.wait_for must be a list of non empty strings')

    def test_gate_steps_and_optional_fields_are_exposed(self):
        for run, expected in (('"check"', ("check",)),
                              ('["check", "test"]', ("check", "test"))):
            with self.subTest(run=run):
                config = parse('[gates]\nabout = ""\nci = ".github/check.yml"\nrun = ' + run,
                               "ladder.toml")
                self.assertEqual(config.gates,
                                 {"about": "", "ci": ".github/check.yml", "run": expected})

    def test_gates_need_non_empty_run(self):
        # Cases: absent, empty, whitespace, wrong type, empty list, invalid list member.
        for run in (None, '""', '"  "', '42', 'true', '[]', '["check", ""]',
                    '["check", "  "]', '["check", 42]', '[["check"]]'):
            with self.subTest(run=run):
                text = '[gates]' + ('\nrun = ' + run if run is not None else '')
                self.assert_bad(text, 'gates: run must be a non empty string or list of non empty strings')

    def test_gates_reject_unknown_keys_including_task_only_options(self):
        for key in ("steps", "shell", "confirm", "extra"):
            with self.subTest(key=key):
                self.assert_bad(f'[gates]\nrun = "check"\n{key} = true',
                                f'gates: unknown key "{key}"')

    def test_gates_about_must_be_text(self):
        for about in ("42", "true", "[]"):
            with self.subTest(about=about):
                self.assert_bad('[gates]\nrun = "check"\nabout = ' + about,
                                'gates: about must be a string')

    def test_gates_ci_must_be_a_non_empty_relative_path(self):
        for ci in ('42', 'true', '[]', '""', '"  "', '"/ci.yml"',
                   "'C:\\checks\\ci.yml'", "'C:ci.yml'", "'\\\\host\\share\\ci.yml'"):
            with self.subTest(ci=ci):
                self.assert_bad('[gates]\nrun = "check"\nci = ' + ci,
                                'gates: ci must be a non empty relative path')

    def test_missing_tasks_gives_empty_dict(self):
        config = parse("", "ladder.toml")
        self.assertEqual(config.tasks, {})
