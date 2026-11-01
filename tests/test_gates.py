import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

from ladder.cli import main
from ladder.config import load
from ladder.process import Runner
from tests.test_tasks import TaskRunner


class GatesCliTests(unittest.TestCase):
    @property
    def using(self):
        return f"ladder: using {self.root / 'ladder.toml'}\n"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / ".git").mkdir()
        (self.root / "nested").mkdir()

    def invoke(self, text, args=(), codes=(0,)):
        path = self.root / "ladder.toml"
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text, encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        runner = TaskRunner(out, codes)
        with patch("os.getcwd", return_value=str(self.root / "nested")):
            code = main(["gates", *args], runner, out, err)
        return code, out.getvalue(), err.getvalue(), runner.steps

    def test_missing_file_or_section_is_a_plain_error(self):
        for text in (None, "", '[tasks.check]\nabout = "Check"\nrun = "check"'):
            with self.subTest(text=text):
                self.assertEqual(self.invoke(text),
                                 (1, "", "ladder: no [gates] in ladder.toml\n", []))

    def test_steps_run_without_shell_from_config_folder_with_pass_lines(self):
        code, out, err, steps = self.invoke(
            '[gates]\nrun = [\'check "file name"\', "test | literal"]', codes=(0, 0))
        self.assertEqual((code, err), (0, self.using))
        self.assertEqual(steps, [(["check", "file name"], str(self.root)),
                                 (["test", "|", "literal"], str(self.root))])
        self.assertEqual(out, '$ check \'file name\'\nPASS step 1 of 2: check "file name"\n'
                              "$ test '|' literal\nPASS step 2 of 2: test | literal\n"
                              "gates: all 2 passed\n")

    def test_first_failed_step_stops_and_returns_its_exit_code(self):
        for codes, expected, lines in (((7,), 7, ["first"]),
                                      ((0, 9), 9, ["first", "second"]),
                                      ((0, 0, 4), 4, ["first", "second", "third"])):
            with self.subTest(codes=codes):
                code, out, err, steps = self.invoke(
                    '[gates]\nrun = ["first", "second", "third"]', codes=codes)
                self.assertEqual((code, err), (expected, self.using))
                self.assertEqual([argv[0] for argv, _ in steps], lines)
                expected_output = ""
                for number, (line, status) in enumerate(zip(lines, codes), 1):
                    expected_output += f"$ {line}\n"
                    expected_output += (f"FAIL step {number} of 3: {line} (exit {status})\n" if status
                                        else f"PASS step {number} of 3: {line}\n")
                self.assertEqual(out, expected_output)

    def test_dry_run_numbers_original_lines_without_starting_anything(self):
        self.assertEqual(self.invoke('[gates]\nrun = [\'check "file name"\', "test"]',
                                     args=("--dry-run",), codes=()),
                         (0, '1: check "file name"\n2: test\n', self.using, []))

    def test_gates_reject_extra_args_and_abbreviated_flags(self):
        for args in (("extra",), ("--yes",), ("--dry",), ("--dry-run", "extra")):
            with self.subTest(args=args):
                code, out, err, steps = self.invoke('[gates]\nrun = "check"', args=args)
                self.assertEqual((code, out, steps), (1, "", []))
                self.assertIn("unrecognized arguments:", err)
                self.assertEqual(len(err.splitlines()), 1)

    def test_gates_help_is_available_without_loading_config(self):
        code, out, err, steps = self.invoke('not TOML', args=("--help",))
        self.assertEqual((code, err, steps), (0, "", []))
        self.assertIn("--dry-run", out)

    def test_ci_whitespace_substring_match_has_positive_and_negative_cases(self):
        ci = self.root / ".github" / "ci.yml"
        ci.parent.mkdir()
        ci.write_text("# caf\u00e9\nrun: python   -m\n unittest -v\n", encoding="utf-8")
        text = '[gates]\nci = ".github/ci.yml"\nrun = "python -m unittest"'
        for matched in (True, False):
            if not matched:
                ci.write_text("run: python -m pytest\n", encoding="utf-8")
            for args in ((), ("--dry-run",)):
                with self.subTest(matched=matched, args=args):
                    code, out, err, steps = self.invoke(text, args=args)
                    self.assertEqual(code, 0)
                    self.assertEqual(err, self.using + ("" if matched else
                                     "warning: gate step 1 not found in .github/ci.yml: python -m unittest\n"))
                    self.assertEqual(len(steps), 0 if args else 1)
                    self.assertIn("1: python -m unittest" if args else "gates: all 1 passed", out)

    def test_ci_match_collapses_whitespace_in_the_gate_too(self):
        (self.root / "ci.yml").write_text("run: check file name", encoding="utf-8")
        code, out, err, steps = self.invoke(
            '[gates]\nci = "ci.yml"\nrun = "check  file\\tname"')
        self.assertEqual((code, err), (0, self.using))
        self.assertEqual(steps, [(["check", "file", "name"], str(self.root))])
        self.assertIn("PASS step 1 of 1: check  file\tname\n", out)

    def test_ci_warnings_name_each_missing_step_before_running(self):
        (self.root / "ci.yml").write_text("second", encoding="utf-8")
        (self.root / "ladder.toml").write_text(
            '[gates]\nci = "ci.yml"\nrun = ["first", "second", "third"]', encoding="utf-8")
        combined = io.StringIO()
        runner = TaskRunner(combined, (0, 0, 0))
        code = main(["gates"], runner, combined, combined, lambda _: load(self.root))
        self.assertEqual(code, 0)
        self.assertEqual(combined.getvalue().splitlines()[:4],
                         [self.using.strip(), "warning: gate step 1 not found in ci.yml: first",
                          "warning: gate step 3 not found in ci.yml: third", "$ first"])
        self.assertEqual(combined.getvalue().count(self.using), 1)

    def test_unreadable_ci_warns_and_preserves_step_exit_code(self):
        # Cases: missing file, invalid UTF8, directory instead of a file.
        ci = self.root / "ci.yml"
        for state in ("missing", "invalid", "directory"):
            if state == "invalid":
                ci.write_bytes(b"\xff")
            elif state == "directory":
                ci.unlink()
                ci.mkdir()
            with self.subTest(state=state):
                code, out, err, steps = self.invoke(
                    '[gates]\nci = "ci.yml"\nrun = "check"', codes=(6,))
                self.assertEqual(code, 6)
                self.assertEqual(len(steps), 1)
                self.assertIn("FAIL step 1 of 1: check (exit 6)", out)
                self.assertTrue(err.startswith(self.using + "warning: could not read ci.yml:"))
                self.assertEqual(len(err.splitlines()), 2)

    def test_malformed_command_has_a_plain_error(self):
        for line in ('check "unclosed', "''"):
            with self.subTest(line=line):
                code, _, err, steps = self.invoke('[gates]\nrun = ' + json.dumps(line))
                self.assertEqual((code, steps), (1, []))
                self.assertTrue(err.startswith(self.using + "ladder: gate step 1: "))
                self.assertEqual(len(err.splitlines()), 2)

    def test_real_runner_streams_child_output_and_stops_on_failure(self):
        script = self.root / "check.py"
        script.write_text("from pathlib import Path\nimport sys\n"
                          "print(Path.cwd().name)\nprint(sys.argv[1:])\n"
                          "sys.exit(int(sys.argv[1]))\n", encoding="utf-8")
        for status in (0, 7):
            with self.subTest(status=status):
                line = shlex.join([sys.executable, "check.py", str(status), "|", "literal"])
                (self.root / "ladder.toml").write_text(
                    '[gates]\nrun = ' + json.dumps([line, line]), encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                code = main(["gates"], Runner(out), out, err, lambda _: load(self.root))
                self.assertEqual((code, err.getvalue()), (status, self.using))
                child_output = self.root.name + f"\n['{status}', '|', 'literal']\n"
                self.assertEqual(out.getvalue().count(child_output), 1 if status else 2)
                self.assertIn(child_output + (f"FAIL step 1 of 2: {line} (exit 7)" if status
                                             else f"PASS step 1 of 2: {line}"), out.getvalue())

    def test_missing_program_reports_start_failure_without_success(self):
        (self.root / "ladder.toml").write_text('[gates]\nrun = "./missing-program"', encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        code = main(["gates"], Runner(out), out, err, lambda _: load(self.root))
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue(), self.using + "ladder: ./missing-program: not found\n")
        self.assertTrue(out.getvalue().endswith("FAIL step 1 of 1: ./missing-program (exit 1)\n"))
