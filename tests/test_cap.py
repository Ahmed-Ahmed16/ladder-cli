import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ladder.cap import Capped
from ladder.cli import Context, main
from ladder.config import Config, Task
from ladder.gates import run_gates
from ladder.process import StepTimeout, redact
from ladder.runlog import logged
from ladder.tasks import run_task


def numbered(count):
    return [f"line {number}\n" for number in range(1, count + 1)]


class CappedTests(unittest.TestCase):
    def test_under_40_lines_show_in_full(self):
        for count in (0, 1, 9, 10, 11, 39):
            with self.subTest(count=count):
                out = io.StringIO()
                cap = Capped(out)
                text = "".join(numbered(count))
                self.assertEqual(cap.write(text), len(text))
                cap.finish("run.log")
                self.assertEqual(out.getvalue(), text)

    def test_exactly_40_lines_show_in_full(self):
        out = io.StringIO()
        cap = Capped(out)
        text = "".join(numbered(40))
        cap.write(text)
        cap.finish("run.log")
        self.assertEqual(out.getvalue(), text)

    def test_300_lines_show_live_head_cut_and_tail(self):
        out = io.StringIO()
        cap = Capped(out)
        lines = numbered(300)
        cap.write("".join(lines))
        self.assertEqual(out.getvalue(), "".join(lines[:10]))
        cap.finish("run.log")
        self.assertEqual(out.getvalue(), "".join([
            *lines[:10],
            "showing 40 of 300 lines (260 cut); full log: run.log\n",
            *lines[-30:]]))

    def test_partial_last_line_counts_as_a_line(self):
        for count in (1, 40, 41, 300):
            with self.subTest(count=count):
                out = io.StringIO()
                cap = Capped(out)
                lines = numbered(count)
                cap.write("".join(lines).rstrip("\n"))
                cap.finish("run.log")
                expected = "".join(lines)
                if count > 40:
                    expected = "".join([
                        *lines[:10],
                        f"showing 40 of {count} lines ({count - 40} cut); full log: run.log\n",
                        *lines[-30:]])
                self.assertEqual(out.getvalue(), expected)

    def test_writes_can_split_a_line(self):
        out = io.StringIO()
        cap = Capped(out)
        cap.write("li")
        self.assertEqual(out.getvalue(), "")
        cap.write("ne 1\nline")
        self.assertEqual(out.getvalue(), "line 1\n")
        cap.write(" 2\n")
        cap.finish("run.log")
        self.assertEqual(out.getvalue(), "line 1\nline 2\n")

    def test_flush_keeps_tail_buffered(self):
        out = io.StringIO()
        cap = Capped(out)
        cap.write("".join(numbered(41)))
        with patch.object(out, "flush") as flush:
            cap.flush()
            flush.assert_called_once_with()
        self.assertEqual(out.getvalue(), "".join(numbered(10)))

    def test_finish_twice_does_not_repeat_output(self):
        out = io.StringIO()
        cap = Capped(out)
        cap.write("".join(numbered(300)).rstrip("\n"))
        cap.finish("run.log")
        expected = out.getvalue()
        cap.finish("other.log")
        self.assertEqual(out.getvalue(), expected)


class OutputRunner:
    def __init__(self, out, lines, code=0, failure=None):
        self.out = out
        self.lines = lines
        self.code = code
        self.failure = failure

    def stream(self, argv, cwd=None):
        print("$ check", file=self.out)
        for line in self.lines:
            self.out.write(redact(line))
        if self.failure is not None:
            raise self.failure
        return self.code


class CappedRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        folder = patch("ladder.runlog.private_folder", return_value=self.root)
        folder.start()
        self.addCleanup(folder.stop)
        self.project = Config(str(self.root / "ladder.toml"),
                              {"check": Task("check", "Check", ("check",))},
                              {"run": ("check",)}, {})

    def invoke(self, agent, *, gates=False, code=0, failure=None):
        out, err = io.StringIO(), io.StringIO()
        runner = OutputRunner(out, numbered(300), code, failure)
        if gates:
            status = run_gates(SimpleNamespace(dry_run=False), self.project, runner, out, agent=agent)
        else:
            status = run_task(self.project, ["check"], runner, out, err,
                              announce=not agent, agent=agent)
        self.assertIs(runner.out, out)
        lines = out.getvalue().splitlines()
        path = Path(lines[-1].rsplit("full log: ", 1)[1])
        return status, lines, path

    def test_agent_task_caps_stdout_and_keeps_full_log(self):
        status, lines, path = self.invoke(True)
        self.assertEqual(status, 0)
        self.assertLessEqual(len(lines), 45)
        summary = f"ladder: ok check, 1 step; full log: {path}"
        self.assertEqual(lines, ["$ check", *[f"line {n}" for n in range(1, 10)],
                                f"showing 40 of 301 lines (261 cut); full log: {path}",
                                *[f"line {n}" for n in range(271, 301)], summary])
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "$ check\n" + "".join(numbered(300)) + summary + "\n")

    def test_human_task_shows_all_output(self):
        status, lines, path = self.invoke(False)
        self.assertEqual(status, 0)
        self.assertEqual(lines, ["$ check", *[f"line {n}" for n in range(1, 301)],
                                f"ladder: ok check, 1 step; full log: {path}"])
        self.assertEqual(path.read_text(encoding="utf-8"), "\n".join(lines) + "\n")

    def test_failed_agent_task_keeps_failure_summary_last(self):
        for code, failure, expected, detail in (
                (3, None, 3, "exit 3"),
                (0, StepTimeout(1), 124, "timeout after 1s (exit 124)")):
            with self.subTest(detail=detail):
                status, lines, path = self.invoke(True, code=code, failure=failure)
                self.assertEqual(status, expected)
                self.assertLessEqual(len(lines), 45)
                self.assertEqual(lines[-1],
                                 f"ladder: FAIL check, step 1 of 1, {detail}; full log: {path}")
                self.assertIn("line 150\n", path.read_text(encoding="utf-8"))

    def test_agent_gates_keep_pass_and_summary_last(self):
        status, lines, path = self.invoke(True, gates=True)
        self.assertEqual(status, 0)
        self.assertLessEqual(len(lines), 45)
        self.assertEqual(lines[10], f"showing 40 of 302 lines (262 cut); full log: {path}")
        self.assertEqual(lines[-2:], ["PASS step 1 of 1: check",
                                     f"gates: all 1 passed; full log: {path}"])
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "$ check\n" + "".join(numbered(300)) + "\n".join(lines[-2:]) + "\n")

    def test_cli_passes_agent_mode_to_tasks_and_gates(self):
        for job in ("check", "gates"):
            for human in (False, True):
                with self.subTest(job=job, human=human):
                    out, err = io.StringIO(), io.StringIO()
                    runner = OutputRunner(out, numbered(300))
                    context = Context(runner, out, err, load_config=lambda _: self.project, agent=True)
                    status = main(["--human", job] if human else [job], context)
                    self.assertEqual(status, 0)
                    text = out.getvalue()
                    self.assertEqual("showing 40 of " in text, not human)
                    self.assertEqual(bool(err.getvalue()), human)
                    if not human:
                        self.assertLessEqual(len(text.splitlines()), 45)

    def test_partial_output_precedes_summary_and_log_stays_complete(self):
        out, err = io.StringIO(), io.StringIO()
        runner = OutputRunner(out, ["partial"])
        status = run_task(self.project, ["check"], runner, out, err, agent=True)
        self.assertEqual(status, 0)
        lines = out.getvalue().splitlines()
        path = Path(lines[-1].rsplit("full log: ", 1)[1])
        self.assertEqual(lines[:2], ["$ check", "partial"])
        self.assertEqual(path.read_text(encoding="utf-8"), out.getvalue())

    def test_exception_finishes_tail_and_restores_runner(self):
        out = io.StringIO()
        runner = OutputRunner(out, ())
        with self.assertRaisesRegex(RuntimeError, "broken"):
            with logged(runner, out, "check", agent=True) as (tee, path):
                tee.write("".join(numbered(300)).rstrip("\n"))
                raise RuntimeError("broken")
        self.assertIs(runner.out, out)
        self.assertIn(f"showing 40 of 300 lines (260 cut); full log: {path}\n", out.getvalue())
        self.assertTrue(out.getvalue().endswith("line 300\n"))
        self.assertEqual(path.read_text(encoding="utf-8"), "".join(numbered(300)).rstrip("\n"))

    def test_log_copy_still_redacts_secrets(self):
        out = io.StringIO()
        runner = OutputRunner(out, ())
        with logged(runner, out, "check", agent=True) as (tee, path):
            tee.write("ghp_ABCDEFGHIJKLMNOP\n")
        self.assertEqual(path.read_text(encoding="utf-8"), "[redacted]\n")
