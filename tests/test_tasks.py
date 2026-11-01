import io
import os
from pathlib import Path
import shlex
import unittest

from ladder.cli import Context, main
from ladder.config import Config, Task
from ladder.process import LadderError
from tests.test_cli import DOCTOR, FakeRunner


class TaskRunner(FakeRunner):
    def __init__(self, out, codes):
        super().__init__(out, DOCTOR)
        self.codes = iter(codes)
        self.steps = []

    def stream(self, argv, cwd=None):
        self.steps.append((argv, cwd))
        print("$ " + shlex.join(argv), file=self.out)
        return next(self.codes)


class TaskCliTests(unittest.TestCase):
    @property
    def using(self):
        return f"ladder: using {Path(os.getcwd()) / 'project' / 'ladder.toml'}\n"

    def invoke(self, argv, tasks=(), codes=(0,), error=None, found=True):
        out, err = io.StringIO(), io.StringIO()
        runner = TaskRunner(out, codes)
        path = str(Path(os.getcwd()) / "project" / "ladder.toml")
        config = Config(path, {task.name: task for task in tasks}, {}, {})
        starts = []

        def load(start):
            starts.append(start)
            if error is not None:
                raise error
            return config if found else None

        code = main(argv, Context(runner, out, err, load_config=load))
        self.assertEqual(starts, [os.getcwd()])
        return code, out.getvalue(), err.getvalue(), runner.steps, config

    def test_list_shows_core_jobs_then_project_tasks(self):
        tasks = [Task("test", "Run tests", ("python tests.py",)),
                 Task("ship-release", "Ship changes", ("ship",), confirm=True)]
        code, out, err, steps, config = self.invoke(["list"], tasks)
        self.assertEqual((code, err, steps), (0, "", []))
        lines = out.splitlines()
        self.assertEqual([line.split()[0] for line in lines[:8]],
                         ["help", "list", "doctor", "pr", "gates", "add", "init", "install-skill"])
        self.assertTrue(all(len(line.split(maxsplit=1)) == 2 for line in lines[:8]))
        self.assertEqual([len(line) - len(line.lstrip()) for line in lines[:8]], [0] * 8)
        for line in lines[:8]:
            name, about = line.split(maxsplit=1)
            self.assertEqual(line.index(about), 15)
        self.assertEqual(lines[4], "gates          run project checks")
        self.assertEqual(lines[5], "add            add a project task to ladder.toml")
        self.assertEqual(lines[8:], [f"Project tasks (from {config.path}):",
                                    "test          Run tests", "ship-release  Ship changes [needs --yes]"])

    def test_list_without_file_succeeds(self):
        code, out, err, steps, _ = self.invoke(["list"], found=False)
        self.assertEqual((code, err, steps), (0, "", []))
        self.assertTrue(out.endswith("no ladder.toml found\n"))

    def test_unknown_task_has_discovery_hint(self):
        for found in (True, False):
            with self.subTest(found=found):
                code, out, err, steps, _ = self.invoke(["missing"], found=found)
                self.assertEqual((code, out, steps), (1, "", []))
                self.assertEqual(err, 'ladder: unknown job or task "missing"; run ladder list\n')

    def test_no_shell_splits_quotes_and_passes_args_from_config_folder(self):
        task = Task("test", "Run tests", ('python "tools/check file.py"',))
        code, out, err, steps, config = self.invoke(["test", "a b", "--flag"], [task])
        self.assertEqual((code, err), (0, self.using))
        self.assertEqual(steps, [(["python", "tools/check file.py", "a b", "--flag"],
                                 str(Path(config.path).parent))])
        self.assertTrue(out.startswith("$ python "))

    def test_task_name_starting_with_dash_is_still_a_task(self):
        task = Task("-check", "Run checks", ("check",))
        code, _, err, steps, _ = self.invoke(["-check"], [task])
        self.assertEqual((code, err), (0, self.using))
        self.assertEqual([argv for argv, _ in steps], [["check"]])

    def test_bash_quotes_extra_args_as_literal_words(self):
        task = Task("test", "Run tests", ("echo ready | cat",), shell="bash")
        code, _, err, steps, config = self.invoke(["test", "a b", "$(bad)", "'"], [task])
        self.assertEqual((code, err), (0, self.using))
        self.assertEqual(steps, [(["bash", "-c", "echo ready | cat " + shlex.join(["a b", "$(bad)", "'"])],
                                 str(Path(config.path).parent))])

    def test_multiple_steps_run_in_order_and_stop_on_failure(self):
        task = Task("test", "Run tests", ("first", "second", "third"))
        for codes, expected_names, expected_code, message in (
                ((0, 0, 0), ["first", "second", "third"], 0, ""),
                ((7,), ["first"], 7, "ladder: step 1 of 3 failed (exit 7)\n"),
                ((0, 9), ["first", "second"], 9, "ladder: step 2 of 3 failed (exit 9)\n")):
            with self.subTest(codes=codes):
                code, _, err, steps, _ = self.invoke(["test"], [task], codes)
                self.assertEqual((code, err), (expected_code, self.using + message))
                self.assertEqual([argv[0] for argv, _ in steps], expected_names)

    def test_extra_args_are_refused_for_multiple_steps(self):
        task = Task("test", "Run tests", ("first", "second"))
        code, out, err, steps, _ = self.invoke(["test", "extra"], [task])
        self.assertEqual((code, out, steps), (1, "", []))
        self.assertEqual(err, 'ladder: task "test" accepts extra args only with 1 run line\n')

    def test_confirm_refuses_without_yes_and_passes_yes_through(self):
        task = Task("ship", "Ship changes", ("ship",), confirm=True)
        for args in ([], ["--yes=true"], ["abc123", "--yes"]):
            with self.subTest(args=args):
                code, _, err, steps, config = self.invoke(["ship", *args], [task])
                if "--yes" in args:
                    self.assertEqual((code, err), (0, self.using))
                    self.assertEqual(steps, [(["ship", *args], str(Path(config.path).parent))])
                else:
                    self.assertEqual((code, err, steps), (1, 'ladder: task "ship" needs --yes\n', []))

    def test_multiple_steps_accept_yes_without_passing_it_to_steps(self):
        for shell in (None, "bash"):
            with self.subTest(shell=shell):
                task = Task("ship", "Ship changes", ("first", "second"),
                            shell=shell, confirm=True)
                code, _, err, steps, config = self.invoke(["ship", "--yes"], [task], (0, 0))
                self.assertEqual((code, err), (0, self.using))
                folder = str(Path(config.path).parent)
                commands = [["first"], ["second"]] if shell is None else [
                    ["bash", "-c", "first"], ["bash", "-c", "second"]]
                self.assertEqual(steps, [(command, folder) for command in commands])

    def test_multiple_steps_with_confirm_refuse_invalid_args(self):
        task = Task("ship", "Ship changes", ("first", "second"), confirm=True)
        for args, message in (([], 'ladder: task "ship" needs --yes\n'),
                              (["--yes", "extra"],
                               'ladder: task "ship" accepts extra args only with 1 run line\n')):
            with self.subTest(args=args):
                code, out, err, steps, _ = self.invoke(["ship", *args], [task])
                self.assertEqual((code, out, steps), (1, "", []))
                self.assertEqual(err, message)

    def test_bad_command_is_a_plain_error(self):
        for line in ('python "unclosed', "''", "   "):
            with self.subTest(line=line):
                code, _, err, steps, _ = self.invoke(["test"], [Task("test", "Run tests", (line,))])
                self.assertEqual((code, steps), (1, []))
                self.assertTrue(err.startswith(self.using + 'ladder: task "test": '))
                self.assertEqual(len(err.splitlines()), 2)

    def test_config_path_printed_once_before_first_step(self):
        combined = io.StringIO()
        project = Config("project/ladder.toml", {
            "check": Task("check", "Check", ("first", "second"))}, {}, {})
        code = main(["check"], Context(TaskRunner(combined, (0, 0)), combined, combined,
                                     load_config=lambda _: project))
        self.assertEqual(code, 0)
        self.assertEqual(combined.getvalue().splitlines(),
                         ["ladder: using project/ladder.toml", "$ first", "$ second"])

    def test_config_error_is_a_plain_error(self):
        for argv in (["list"], ["test"]):
            with self.subTest(argv=argv):
                code, out, err, steps, _ = self.invoke(argv, error=LadderError("file: broken\nTOML"))
                self.assertEqual((code, out, err, steps), (1, "", "ladder: file: broken TOML\n", []))

    def test_doctor_reports_config_or_absence(self):
        for found in (True, False):
            with self.subTest(found=found):
                tasks = [Task("test", "Run tests", ("test",))]
                code, out, err, _, config = self.invoke(["doctor"], tasks, found=found)
                self.assertEqual((code, err), (0, ""))
                label = f"{config.path} (1 tasks)" if found else "none in this repo"
                self.assertIn(f"ok   ladder.toml: {label}\n", out)
                self.assertTrue(out.endswith("doctor: all checks passed\n"))

    def test_doctor_reports_config_errors(self):
        error = LadderError("file: broken")
        code, out, err, _, _ = self.invoke(["doctor"], error=error)
        self.assertEqual((code, err), (1, ""))
        self.assertIn(f"FAIL ladder.toml: {error}\n", out)
        self.assertIn("ok   Python", out)
        self.assertTrue(out.endswith("doctor: 1 check(s) failed\n"))
