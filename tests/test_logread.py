import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ladder.cli import Context, main
from ladder.logread import read_log
from ladder.process import LadderError


class LogReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()
        folder = patch("ladder.runlog.private_folder", return_value=self.logs)
        folder.start()
        self.addCleanup(folder.stop)
        self.path = self.write_log("test-20261116-120000.log",
                                   "".join(f"line-{n}\n" for n in range(1, 301)))

    def write_log(self, name, text):
        path = self.logs / name
        path.write_text(text, encoding="utf-8")
        return path

    def invoke(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        def no_project(_):
            raise AssertionError("log must not read project config")

        code = main(["log", *map(str, argv)], Context(None, out, err, load_config=no_project))
        return code, out.getvalue().splitlines(), err.getvalue()

    def test_grep_finds_line_150_in_300_lines(self):
        code, lines, err = self.invoke(self.path, "--grep", "^line-150$")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines, [f"showing 1 of 300 lines in {self.path.name}", "line-150"])
        self.assertLessEqual(len(lines), 10)

    def test_head_and_tail(self):
        for option, expected in (("--head", ["line-1", "line-2"]),
                                 ("--tail", ["line-299", "line-300"])):
            with self.subTest(option=option):
                code, lines, err = self.invoke(self.path, option, "2")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(lines, [f"showing 2 of 300 lines in {self.path.name}", *expected])

    def test_grep_runs_before_head_or_tail(self):
        for option, expected in (("--head", ["line-10", "line-20"]),
                                 ("--tail", ["line-290", "line-300"])):
            with self.subTest(option=option):
                code, lines, err = self.invoke(self.path, "--grep", "0$", option, "2")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(lines[1:], expected)

    def test_head_and_tail_together_raise_ladder_error(self):
        code, lines, err = self.invoke(self.path, "--head", "1", "--tail", "1")
        self.assertEqual((code, lines), (1, []))
        self.assertIn("--head and --tail cannot be used together", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_default_is_last_40(self):
        code, lines, err = self.invoke(self.path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines, [f"showing 40 of 300 lines in {self.path.name}",
                                 *[f"line-{n}" for n in range(261, 301)]])

    def test_grep_alone_is_last_40_matches(self):
        code, lines, err = self.invoke(self.path, "--grep", "[02468]$")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines, [f"showing 40 of 300 lines in {self.path.name}",
                                 *[f"line-{n}" for n in range(222, 301, 2)]])

    def test_max_chars_cuts_at_a_line_end_or_inside_the_first_line(self):
        for text, options, expected in (
                ("alpha\nbravo\ncharlie\n", ("--head", "3", "--max-chars", "9"),
                 ["showing 1 of 3 lines in short.log", "alpha", "(cut at 9 chars)"]),
                ("abcdef\n", ("--max-chars", "1"),
                 ["showing 1 of 1 lines in short.log", "a", "(cut at 1 chars)"])):
            with self.subTest(options=options):
                path = self.write_log("short.log", text)
                code, lines, err = self.invoke(path, *options)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(lines, expected)

    def test_default_character_cap_is_4000(self):
        path = self.write_log("wide.log", ("x" * 100 + "\n") * 40)
        code, lines, err = self.invoke(path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines[0], "showing 39 of 40 lines in wide.log")
        self.assertEqual(lines[-1], "(cut at 4000 chars)")
        self.assertEqual(lines[1:-1], ["x" * 100] * 39)

    def test_no_match_exits_1(self):
        code, lines, err = self.invoke(self.path, "--grep", "absent")
        self.assertEqual((code, err), (1, ""))
        self.assertEqual(lines, [f"showing 0 of 300 lines in {self.path.name}", "no lines match"])

    def test_invalid_regex_reports_one_short_error(self):
        code, lines, err = self.invoke(self.path, "--grep", "[")
        self.assertEqual((code, lines), (1, []))
        self.assertIn("invalid --grep regex:", err)
        self.assertEqual(len(err.splitlines()), 1)

    def test_name_lookup_uses_newest_modification_time(self):
        older = self.write_log("gates-20261116-120000.log", "older\n")
        newest = self.write_log("gates-20261115-120000.log", "newest\n")
        exact = self.write_log("gates.log", "exact\n")
        self.write_log("gates-extra.txt", "wrong suffix\n")
        self.write_log("gateskeeper.log", "wrong prefix\n")
        for path, stamp in ((older, 10), (newest, 30), (exact, 20)):
            os.utime(path, ns=(stamp * 1_000_000_000, stamp * 1_000_000_000))
        for name in ("gates", "gates.log"):
            with self.subTest(name=name):
                code, lines, err = self.invoke(name)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(lines, [f"showing 1 of 1 lines in {newest.name}", "newest"])

    def test_file_names_work_with_or_without_log_suffix(self):
        for name in (self.path.name, self.path.stem):
            with self.subTest(name=name):
                code, lines, err = self.invoke(name, "--head", "1")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(lines[-1], "line-1")

    def test_missing_log_has_required_error(self):
        for name in ("absent", self.logs / "absent.log"):
            with self.subTest(name=name):
                with self.assertRaises(LadderError) as caught:
                    read_log(str(name))
                self.assertEqual(str(caught.exception), f"no log found for {name}")

    def test_outside_path_is_rejected(self):
        outside = self.root / "outside.log"
        outside.write_text("private\n", encoding="utf-8")
        with self.assertRaises(LadderError) as caught:
            read_log(str(outside))
        self.assertEqual(str(caught.exception), f"{outside}: not a ladder log")

    def test_nested_non_log_and_directory_paths_are_rejected(self):
        nested = self.logs / "nested"
        nested.mkdir()
        child = nested / "child.log"
        child.write_text("nested\n", encoding="utf-8")
        wrong_suffix = self.write_log("plain.txt", "text\n")
        directory = self.logs / "folder.log"
        directory.mkdir()
        for path in (child, wrong_suffix, directory, Path("nested/child.log")):
            with self.subTest(path=path):
                with self.assertRaises(LadderError) as caught:
                    read_log(str(path))
                self.assertEqual(str(caught.exception), f"{path}: not a ladder log")

    def test_symlinks_are_rejected_even_with_an_internal_target(self):
        outside = self.root / "outside.log"
        outside.write_text("private\n", encoding="utf-8")
        for target in (outside, self.path):
            link = self.logs / ("escape.log" if target == outside else "inside.log")
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks cannot be created")
            for name in (str(link), link.name):
                with self.subTest(name=name):
                    with self.assertRaises(LadderError) as caught:
                        read_log(name)
                    self.assertEqual(str(caught.exception), f"{name}: not a ladder log")

    def test_log_tokens_stay_redacted(self):
        secret = "ghp_MADE_UP_SECRET_DO_NOT_USE_1234567890"
        path = self.write_log("secret.log", f"token={secret}\n")
        code, lines, err = self.invoke(path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines[1:], ["token=[redacted]"])
        self.assertNotIn(secret, "\n".join(lines))

    def test_redaction_precedes_character_cuts(self):
        path = self.write_log("secret.log", 'password="private value"\n')
        code, lines, err = self.invoke(path, "--max-chars", "15")
        self.assertEqual((code, err), (0, ""))
        self.assertNotIn("private", "\n".join(lines))
        self.assertEqual(lines[-1], "(cut at 15 chars)")

    def test_each_line_has_at_most_300_characters(self):
        path = self.write_log("wide.log", "x" * 300 + "\n" + "y" * 301 + "\n")
        code, lines, err = self.invoke(path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines[1:], ["x" * 300, "y" * 297 + "..."])

    def test_bad_utf8_is_replaced(self):
        path = self.logs / "bytes.log"
        path.write_bytes(b"before\xffafter\n")
        code, lines, err = self.invoke(path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines[1:], ["before\ufffdafter"])

    def test_empty_log_succeeds_without_grep(self):
        path = self.write_log("empty.log", "")
        code, lines, err = self.invoke(path)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(lines, ["showing 0 of 0 lines in empty.log"])

    def test_counts_must_be_positive_whole_numbers(self):
        for option in ("--head", "--tail", "--max-chars"):
            for value in ("0", "-1", "1.5", "x", "\u0661", "9" * 5000):
                with self.subTest(option=option, value=value[:10]):
                    code, lines, err = self.invoke(self.path, option, value)
                    self.assertEqual((code, lines), (1, []))
                    self.assertIn("must be a whole number >= 1", err)
