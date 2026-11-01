import unittest
from unittest.mock import patch

from ladder.config import parse
from tests.test_setup import SetupCase


class AddCliTests(SetupCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        (self.repo / ".git").mkdir()
        self.path = self.repo / "ladder.toml"

    def test_add_preserves_existing_bytes_and_appends_separated_block(self):
        # Cases: empty file, LF, CRLF, missing final newline, existing blank line.
        base = b'# caf\xc3\xa9\r\n[tasks.old]\r\nabout = "Keep"\r\nrun = "keep"'
        for original in (b"", base + b"\n", base + b"\r\n", base, base + b"\n\n"):
            with self.subTest(original=original):
                self.path.write_bytes(original)
                code, out, err = self.invoke("add", "check-lang", "--about", "Find missing keys",
                                             "--run", "python scripts/ladder/check-lang.py")
                self.assertEqual((code, err), (0, ""))
                separator = b"\n" if original.endswith(b"\n") else b"\n\n"
                block = (b'[tasks.check-lang]\nabout = "Find missing keys"\n'
                         b'run = "python scripts/ladder/check-lang.py"\n')
                self.assertEqual(self.path.read_bytes(), original + separator + block)
                project = parse(self.path.read_bytes().decode("utf-8"), str(self.path))
                self.assertEqual(project.tasks["check-lang"].run,
                                 ("python scripts/ladder/check-lang.py",))
                self.assertEqual(out, f'added task "check-lang" to {self.path}\n'
                                     'run it once: ladder check-lang\n')
                self.assertFalse((self.child / "ladder.toml").exists())

    def test_missing_file_is_created_with_only_the_block(self):
        self.assertEqual(self.invoke("add", "check", "--about", "Check", "--run", "check"),
                         (0, f'added task "check" to {self.path}\nrun it once: ladder check\n', ""))
        self.assertEqual(self.path.read_bytes(), b'[tasks.check]\nabout = "Check"\nrun = "check"\n')

    def test_multiple_runs_are_saved_as_a_list_in_order(self):
        code, _, err = self.invoke("add", "check", "--about", "Check", "--run", "first",
                                   "--run", "second")
        self.assertEqual((code, err), (0, ""))
        text = self.path.read_text(encoding="utf-8")
        self.assertIn('run = ["first", "second"]\n', text)
        self.assertEqual(parse(text, str(self.path)).tasks["check"].run, ("first", "second"))

    def test_shell_and_confirm_are_saved_when_given(self):
        for options, shell, confirm in ((["--shell", "bash"], "bash", False),
                                         (["--confirm"], None, True),
                                         (["--shell", "bash", "--confirm"], "bash", True)):
            with self.subTest(options=options):
                self.path.unlink(missing_ok=True)
                code, _, err = self.invoke("add", "check", "--about", "Check", "--run", "check",
                                           *options)
                self.assertEqual((code, err), (0, ""))
                task = parse(self.path.read_text(encoding="utf-8"), str(self.path)).tasks["check"]
                self.assertEqual((task.shell, task.confirm), (shell, confirm))

    def test_duplicate_task_refuses_unchanged_and_names_the_existing_script(self):
        # Cases: table, quoted table, dotted keys, inline table, invalid schema.
        originals = [b'[tasks.check]\nabout = "Keep"\nrun = "keep"',
                     b'[tasks."check"]\nabout = "Keep"\nrun = "keep"',
                     b'tasks.check.about = "Keep"\ntasks.check.run = "keep"',
                     b'tasks = {check = {about = "Keep", run = "keep"}}',
                     b'[tasks.check]\nabout = ""\nrun = "keep"',
                     b'[unknown]\n[tasks.check]\nabout = "Keep"\nrun = "keep"']
        for original in originals:
            with self.subTest(original=original):
                self.path.write_bytes(original)
                self.assertEqual(self.invoke("add", "check", "--about", "New", "--run", "new"),
                                 (1, "", 'ladder: task "check" already exists; edit its script instead\n'))
                self.assertEqual(self.path.read_bytes(), original)

    def test_core_names_refuse_without_creating_a_file(self):
        for name in ("help", "list", "doctor", "pr", "gates", "add", "init", "install-skill"):
            with self.subTest(name=name):
                code, out, err = self.invoke("add", name, "--about", "Check", "--run", "check")
                self.assertEqual((code, out), (1, ""))
                self.assertIn(f'task "{name}" clashes with the core job "{name}"', err)
                self.assertFalse(self.path.exists())

    def test_invalid_names_refuse_without_changing_existing_file(self):
        original = b"# keep\r\n"
        self.path.write_bytes(original)
        for name in ("", "a.b", "a b", "a/b", 'a"b', "caf\u00e9", "a\n"):
            with self.subTest(name=name):
                code, out, err = self.invoke("add", name, "--about", "Check", "--run", "check")
                self.assertEqual((code, out), (1, ""))
                self.assertIn("name must contain only letters, digits, - and _", err)
                self.assertEqual(len(err.splitlines()), 1)
                self.assertEqual(self.path.read_bytes(), original)

    def test_bare_names_allow_digits_underscores_and_dashes(self):
        for name in ("123", "Check_9-ok", "-check"):
            with self.subTest(name=name):
                code, _, err = self.invoke("add", "--about", "Check", "--run", "check", "--", name)
                self.assertEqual((code, err), (0, ""))
                self.assertIn(name, parse(self.path.read_text(encoding="utf-8"), str(self.path)).tasks)

    def test_outside_repo_refuses_and_ignores_parent_config(self):
        parent_path = self.root / "ladder.toml"
        parent_path.write_bytes(b"# leave alone\r\n")
        self.assertEqual(self.invoke("add", "check", "--about", "Check", "--run", "check",
                                     start=self.root),
                         (1, "", "ladder: not in a git repo\n"))
        self.assertEqual(parent_path.read_bytes(), b"# leave alone\r\n")
        self.assertFalse(self.path.exists())

    def test_windows_path_quotes_and_controls_round_trip_exactly(self):
        line = 'python "C:\\tools\\check.py" "say \\"hi\\""\targ'
        controls = "".join(chr(number) for number in range(32)) + "\x7f"
        about = 'Check "caf\u00e9" ' + controls
        code, _, err = self.invoke("add", "check", "--about", about, "--run", line + controls)
        self.assertEqual((code, err), (0, ""))
        task = parse(self.path.read_bytes().decode("utf-8"), str(self.path)).tasks["check"]
        self.assertEqual((task.about, task.run), (about, (line + controls,)))

    def test_required_arguments_and_invalid_shell_refuse_before_creating_file(self):
        cases = [((), "name"), (("check", "--run", "check"), "--about"),
                 (("check", "--about", "Check"), "--run"),
                 (("check", "--about", "Check", "--run", "check", "--shell", "sh"), "--shell")]
        for args, message in cases:
            with self.subTest(args=args):
                code, out, err = self.invoke("add", *args)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(message, err)
                self.assertFalse(self.path.exists())

    def test_invalid_existing_or_new_config_refuses_unchanged(self):
        cases = [(b"not TOML", "Check", "check", "not valid TOML"),
                 (b"[unknown]\n", "Check", "check", "unknown section"),
                 (b'tasks = ["check"]\n', "Check", "check", "not valid TOML"),
                 (b"# keep\r\n", " ", "check", "about must be a non empty string"),
                 (b"# keep\r\n", "Check", " ", "run must be a non empty string"),
                 (b"\xff", "Check", "check", "decode")]
        for original, about, line, message in cases:
            with self.subTest(original=original, about=about, line=line):
                self.path.write_bytes(original)
                code, out, err = self.invoke("add", "check", "--about", about, "--run", line)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(message, err)
                self.assertEqual(self.path.read_bytes(), original)

    def test_failed_atomic_replace_keeps_original_and_cleans_temporary_file(self):
        original = b"# keep\r\n"
        self.path.write_bytes(original)
        before = set(self.repo.iterdir())
        with patch("ladder.setup.os.replace", side_effect=PermissionError("replace denied")):
            self.assertEqual(self.invoke("add", "check", "--about", "Check", "--run", "check"),
                             (1, "", "ladder: replace denied\n"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(set(self.repo.iterdir()), before)

    def test_add_help_needs_no_repo_or_valid_config(self):
        self.path.write_bytes(b"not TOML")
        code, out, err = self.invoke("add", "--help", start=self.root)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("--about", out)
        self.assertIn("--run", out)
        self.assertEqual(self.path.read_bytes(), b"not TOML")
