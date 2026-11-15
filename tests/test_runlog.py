import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from ladder.cli import Context, main
from ladder.config import Config, Task
from ladder.process import (LadderError, Runner, StepTimeout, WINDOWS, bash_program,
                            expire_step)
from ladder.runlog import create_log, private_folder


try:
    BASH = bash_program()
except LadderError:
    BASH = None


class OutputRunner:
    def __init__(self, out, lines, code):
        self.out = out
        self.lines = lines
        self.code = code

    def stream(self, argv, cwd=None):
        for line in self.lines:
            print(line, file=self.out)
        return self.code


class RunLogTests(unittest.TestCase):
    def setUp(self):
        previous = tempfile.tempdir
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(setattr, tempfile, "tempdir", previous)
        self.root = Path(temporary.name).resolve()
        tempfile.tempdir = str(self.root)
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("LADDER_TIMEOUT", None)

    def invoke(self, lines=(), code=0):
        out, err = io.StringIO(), io.StringIO()
        runner = OutputRunner(out, lines, code)
        project = Config(str(self.root / "ladder.toml"),
                         {"check": Task("check", "Check", ("check",))}, {}, {})
        status = main(["check"], Context(runner, out, err, load_config=lambda _: project))
        self.assertEqual(err.getvalue(), f"ladder: using {project.path}\n")
        return status, out.getvalue()

    def log_path(self, out):
        last = out.splitlines()[-1]
        self.assertIn("; full log: ", last)
        path = Path(last.rsplit("full log: ", 1)[1])
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.root / "ladder" / "logs")
        return path

    def test_failed_task_keeps_all_output_before_final_summary(self):
        lines = [f"line {number}" for number in range(300)]
        code, out = self.invoke(lines, 3)
        self.assertEqual(code, 3)
        last = out.splitlines()[-1]
        self.assertTrue(last.startswith("ladder: FAIL"))
        self.assertFalse(last.startswith("ladder: ok"))
        path = self.log_path(out)
        self.assertEqual(last,
                         f"ladder: FAIL check, step 1 of 1, exit 3; full log: {path}")
        self.assertEqual(path.read_text(encoding="utf-8").splitlines(), [*lines, last])

    def test_passing_task_ends_with_ok_summary(self):
        code, out = self.invoke()
        self.assertEqual(code, 0)
        path = self.log_path(out)
        self.assertTrue(out.splitlines()[-1].startswith("ladder: ok"))
        self.assertEqual(out.splitlines()[-1], f"ladder: ok check, 1 step; full log: {path}")

    def test_log_redacts_tokens_from_runner_output(self):
        secret = "ghp_ABCDEFGHIJKLMNOP"
        code, out = self.invoke([secret])
        self.assertEqual(code, 0)
        text = self.log_path(out).read_text(encoding="utf-8")
        self.assertIn("[redacted]", text)
        self.assertNotIn(secret, text)

    def test_same_second_runs_keep_existing_logs(self):
        stamp = "20261115-123456"
        directory = self.root / "ladder" / "logs"
        directory.mkdir(parents=True)
        existing = directory / f"check-{stamp}.log"
        existing.write_text("existing\n", encoding="utf-8")
        paths = []
        with patch("ladder.runlog.time.strftime", return_value=stamp):
            for suffix in ("-2", "-3"):
                with self.subTest(suffix=suffix):
                    code, out = self.invoke()
                    self.assertEqual(code, 0)
                    path = self.log_path(out)
                    self.assertEqual(path.name, f"check-{stamp}{suffix}.log")
                    paths.append(path)
        self.assertNotEqual(paths[0], paths[1])
        self.assertEqual(existing.read_text(encoding="utf-8"), "existing\n")

    @unittest.skipUnless(BASH, "bash is unavailable")
    def test_bash_task_preserves_pipeline_failure(self):
        for line, expected in (("exit 5 | cat", 5), ("true | cat", 0)):
            with self.subTest(line=line):
                project = Config(str(self.root / "ladder.toml"), {
                    "check": Task("check", "Check", (line,), shell="bash")}, {}, {})
                out, err = io.StringIO(), io.StringIO()
                code = main(["check"], Context(Runner(out), out, err,
                                             load_config=lambda _: project))
                self.assertEqual(code, expected)
                self.assertEqual(err.getvalue(), f"ladder: using {project.path}\n")
                self.log_path(out.getvalue())

    def test_timeout_stops_real_child_and_reports_seconds(self):
        out = io.StringIO()
        started = time.monotonic()
        with patch.dict(os.environ, LADDER_TIMEOUT="1"):
            with self.assertRaises(StepTimeout) as raised:
                Runner(out).stream([sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(raised.exception.seconds, 1)

    def test_unset_timeout_preserves_fast_child_exit_code(self):
        self.assertNotIn("LADDER_TIMEOUT", os.environ)
        code = Runner(io.StringIO()).stream([sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(code, 7)

    def test_invalid_timeout_is_a_plain_error(self):
        for value in ("0", "abc", "nan", "inf", "-1"):
            with self.subTest(value=value), patch.dict(os.environ, LADDER_TIMEOUT=value):
                with self.assertRaisesRegex(LadderError, "LADDER_TIMEOUT"):
                    Runner(io.StringIO()).stream([sys.executable, "-c", "raise SystemExit(0)"])

    def test_expire_step_leaves_a_child_that_already_exited(self):
        child = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(child.wait(), 7)
        expired = threading.Event()
        expire_step(child, expired)
        self.assertFalse(expired.is_set())

    def test_expire_step_kills_a_running_child(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 start_new_session=not WINDOWS)
        self.addCleanup(child.kill)
        expired = threading.Event()
        expire_step(child, expired)
        self.assertTrue(expired.is_set())
        self.assertNotEqual(child.wait(timeout=10), 0)

    def test_log_file_is_never_reused(self):
        path = private_folder() / "check.log"
        create_log(path).close()
        with self.assertRaises(FileExistsError):
            create_log(path)

    @unittest.skipUnless(hasattr(os, "getuid"), "owner checks need POSIX")
    def test_log_folder_and_files_are_private(self):
        folder = private_folder()
        self.assertEqual(folder.stat().st_mode & 0o077, 0)
        path = folder / "check.log"
        create_log(path).close()
        self.assertEqual(path.stat().st_mode & 0o077, 0)
        folder.chmod(0o755)
        with self.assertRaisesRegex(LadderError, "private folder"):
            private_folder()

    @unittest.skipUnless(hasattr(os, "getuid"), "links need POSIX")
    def test_log_folder_that_is_a_link_is_refused(self):
        target = self.root / "elsewhere"
        target.mkdir()
        (self.root / "ladder").mkdir()
        (self.root / "ladder" / "logs").symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(LadderError, "private folder"):
            private_folder()

    def run_cli(self, name, script, timeout=None):
        project = self.root / "project"
        project.mkdir(exist_ok=True)
        (project / ".git").mkdir(exist_ok=True)
        command = shlex.join([sys.executable, "-c", script])
        (project / "ladder.toml").write_text(
            f'[tasks.{name}]\nabout = "Check"\nrun = ' + json.dumps(command) + "\n",
            encoding="utf-8")
        environment = os.environ.copy()
        environment.update({
            "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            "TMP": str(self.root), "TEMP": str(self.root), "TMPDIR": str(self.root)})
        if timeout is not None:
            environment["LADDER_TIMEOUT"] = timeout
        return subprocess.run([sys.executable, "-m", "ladder", name], cwd=project,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace",
                              env=environment, timeout=15, check=False)

    def test_cli_last_line_is_task_summary(self):
        for name, script, timeout, expected, result in (
                ("fail", "print('failed'); raise SystemExit(3)", None, 3,
                 "ladder: FAIL fail, step 1 of 1, exit 3"),
                ("pass", "print('passed')", None, 0, "ladder: ok pass, 1 step"),
                ("timeout", "import time; time.sleep(30)", "1", 124,
                 "ladder: FAIL timeout, step 1 of 1, timeout after 1s (exit 124)")):
            with self.subTest(name=name):
                child = self.run_cli(name, script, timeout)
                self.assertEqual(child.returncode, expected, child.stdout)
                lines = child.stdout.splitlines()
                path = self.log_path(child.stdout)
                self.assertEqual(lines[-1], f"{result}; full log: {path}")
                self.assertEqual(sum(line.startswith(("ladder: FAIL", "ladder: ok"))
                                     for line in lines), 1)
                self.assertEqual(path.read_text(encoding="utf-8").splitlines()[-1], lines[-1])
