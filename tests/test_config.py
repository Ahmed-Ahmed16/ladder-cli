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

    def test_gates_are_validated_while_review_is_kept(self):
        config = parse('[gates]\nrun = "check"\n[review]\nwait_for = "later"', "ladder.toml")
        self.assertEqual(config.gates, {"run": ("check",)})
        self.assertEqual(config.review, {"wait_for": "later"})

    def test_gate_steps_and_optional_fields_are_exposed(self):
        for run, expected in (('"check"', ("check",)),
                              ('["check", "test"]', ("check", "test"))):
            with self.subTest(run=run):
                config = parse('[gates]\nabout = ""\nci = ".github/check.yml"\nrun = ' + run,
                               "ladder.toml")
                self.assertEqual(config.gates,
                                 {"about": "", "ci": ".github/check.yml", "run": expected})

    def test_gates_must_be_a_table(self):
        self.assert_bad('gates = []', 'gates: must be a table')

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
