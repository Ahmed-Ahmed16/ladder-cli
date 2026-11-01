import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from ladder.cli import Context, main
from ladder.config import parse
from ladder.process import LadderError, Runner


class RunnerTests(unittest.TestCase):
    def test_stream_runs_from_cwd_and_preserves_exit_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "tools").mkdir()
            script = root / "tools" / "check.py"
            script.write_text('from pathlib import Path\nimport sys\n'
                              'print(Path.cwd().name)\n'
                              'print("ghp_MADE_UP_SECRET")\nsys.exit(7)\n', encoding="utf-8")
            out = io.StringIO()
            code = Runner(out).stream([sys.executable, "tools/check.py"], cwd=str(root))
            self.assertEqual(code, 7)
            self.assertIn(root.name + "\n[redacted]\n", out.getvalue())
            self.assertTrue(out.getvalue().startswith("$ "))

    def test_explicit_program_paths_use_cwd_without_path_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            program = root / "tools" / "runner.exe"
            program.parent.mkdir()
            program.touch()
            program.chmod(0o755)
            for name in ("./tools/runner.exe", "tools/runner.exe", str(program)):
                with self.subTest(name=name), patch.dict(os.environ, PATH=""):
                    self.assertEqual(Runner(io.StringIO())._argv([name, "arg"], cwd=str(root)),
                                     [str(program), "arg"])
            with self.assertRaises(LadderError) as raised:
                Runner(io.StringIO()).stream(["./missing.exe"], cwd=str(root))
            self.assertEqual(str(raised.exception), "./missing.exe: not found")

    def test_stream_passes_resolved_relative_program_to_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            program = root / "tools" / "runner.exe"
            program.parent.mkdir()
            program.touch()
            out = io.StringIO()
            with patch("ladder.process.subprocess.Popen") as popen:
                child = popen.return_value.__enter__.return_value
                child.stdout = iter(["child output\n"])
                child.wait.return_value = 3
                code = Runner(out).stream(["tools/runner.exe", "arg"], cwd=str(root))
                self.assertEqual(popen.call_args.args[0], [str(program), "arg"])
                self.assertEqual(popen.call_args.kwargs["cwd"], str(root))
            self.assertEqual(code, 3)
            self.assertTrue(out.getvalue().endswith("child output\n"))
            with patch.dict(os.environ, PATH=str(program.parent)):
                with self.assertRaises(LadderError) as raised:
                    Runner(io.StringIO()).stream(["./runner.exe"], cwd=str(root))
            self.assertEqual(str(raised.exception), "./runner.exe: not found")

    def test_current_folder_program_is_not_found_through_unsafe_path_entries(self):
        # Cases: empty, dot, relative, and an absolute PATH folder without the program.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            program = root / 'ladder-test-tool.exe'
            program.touch()
            program.chmod(0o755)
            (root / 'bin').mkdir()
            original_cwd = os.getcwd()
            try:
                os.chdir(root)
                for path in ('', '.', 'bin', str(root / 'bin'),
                             os.pathsep.join(('', '.', 'bin', str(root / 'bin')))):
                    with self.subTest(path=path), patch.dict(os.environ, PATH=path):
                        with self.assertRaises(LadderError) as raised:
                            Runner(io.StringIO())._argv([program.name])
                        self.assertEqual(str(raised.exception), 'ladder-test-tool.exe: not found')
            finally:
                os.chdir(original_cwd)


    def test_program_in_absolute_path_folder_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'bin').mkdir()
            original_cwd = os.getcwd()
            try:
                os.chdir(root)
                for folder in (root / 'bin', root):
                    with self.subTest(folder=folder):
                        program = folder / 'ladder-test-tool.exe'
                        program.touch()
                        program.chmod(0o755)
                        planted = root / program.name
                        planted.touch()
                        planted.chmod(0o755)
                        with patch.dict(os.environ, PATH=str(folder)):
                            command = Runner(io.StringIO())._argv([program.name, '--version'])
                        self.assertEqual(command, [str(program), '--version'])
            finally:
                os.chdir(original_cwd)


class BashRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        environment = patch.dict(os.environ, {
            "PATH": "", "PATHEXT": ".exe", "SystemRoot": str(self.root / "Windows")
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.runner = Runner(io.StringIO())

    def program(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        path.chmod(0o755)
        return path

    def on_path(self, *folders):
        os.environ["PATH"] = os.pathsep.join(str(folder) for folder in folders)

    def test_override_wins_even_when_path_has_wsl_or_git_bash(self):
        override = self.program("custom bash/bash.exe")
        git = self.program("Git/cmd/" + ("git.exe" if os.name == "nt" else "git"))
        self.program("Git/bin/bash.exe")
        wsl = self.program("Windows/System32/bash.exe")
        self.on_path(wsl.parent, git.parent)
        os.environ["LADDER_BASH"] = str(override)
        for platform in ("win32", "linux"):
            with self.subTest(platform=platform), patch("ladder.process.WINDOWS", platform == "win32"):
                self.assertEqual(self.runner._argv(["bash", "-c", "echo hi"]),
                                 [str(override), "-c", "echo hi"])

    def test_bad_override_never_falls_back_to_path(self):
        bash = self.program("bin/bash.exe" if os.name == "nt" else "bin/bash")
        self.on_path(bash.parent)
        # Cases: missing file, directory, explicitly set empty string.
        for override in (str(self.root / "missing.exe"), str(bash.parent), ""):
            with self.subTest(override=override):
                os.environ["LADDER_BASH"] = override
                with self.assertRaises(LadderError) as raised:
                    self.runner._argv(["bash", "-c", "echo hi"])
                self.assertIn("LADDER_BASH", str(raised.exception))

    def test_windows_prefers_git_bash_for_each_git_layout(self):
        # Regression: System32 bash starts WSL instead of the project's tools.
        wsl = self.program("Windows/System32/bash.exe")
        for layout in ("cmd", "bin", "mingw64/bin"):
            with self.subTest(layout=layout), patch("ladder.process.WINDOWS", True):
                git = self.program(f"Git/{layout}/" + ("git.exe" if os.name == "nt" else "git"))
                bash = self.program("Git/bin/bash.exe")
                self.on_path(wsl.parent, git.parent)
                self.assertEqual(self.runner._argv(["bash", "-c", "check"]),
                                 [str(bash), "-c", "check"])

    def test_path_bash_is_used_without_a_git_bash_candidate(self):
        bash = self.program("tools/bash.exe" if os.name == "nt" else "tools/bash")
        for layout in (None, "cmd", "other"):
            with self.subTest(layout=layout), patch("ladder.process.WINDOWS", True):
                folders = [bash.parent]
                if layout:
                    git = self.program(f"Git/{layout}/" + ("git.exe" if os.name == "nt" else "git"))
                    folders.insert(0, git.parent)
                self.on_path(*folders)
                self.assertEqual(self.runner._argv(["bash"]), [str(bash)])

    def test_windows_refuses_wsl_locations_but_not_similar_folder_names(self):
        for folder, refused in (("Windows/System32", True),
                                ("Windows/System32/nested", True),
                                ("Local/Microsoft/WindowsApps", True),
                                ("Local/windowsapps/nested", True),
                                ("Windows/System32-tools", False),
                                ("Other/System32", False),
                                ("WindowsApps-tools", False)):
            with self.subTest(folder=folder), patch("ladder.process.WINDOWS", True):
                bash = self.program(folder + ("/bash.exe" if os.name == "nt" else "/bash"))
                self.on_path(bash.parent)
                if refused:
                    with self.assertRaises(LadderError) as raised:
                        self.runner._argv(["bash"])
                    self.assertEqual(str(raised.exception),
                                     "bash: only WSL bash found; install Git for Windows or set LADDER_BASH")
                else:
                    self.assertEqual(self.runner._argv(["bash"]), [str(bash)])

    def test_non_windows_uses_path_even_with_git_or_windows_folder_names(self):
        git = self.program("Git/cmd/" + ("git.exe" if os.name == "nt" else "git"))
        self.program("Git/bin/bash.exe")
        bash = self.program("Windows/System32/bash.exe" if os.name == "nt"
                            else "Windows/System32/bash")
        self.on_path(bash.parent, git.parent)
        with patch("ladder.process.WINDOWS", False):
            self.assertEqual(self.runner._argv(["bash"]), [str(bash)])

    def test_missing_bash_has_plain_not_found_error(self):
        with self.assertRaises(LadderError) as raised:
            self.runner._argv(["bash"])
        self.assertEqual(str(raised.exception), "bash: not found")

    def test_path_lookup_does_not_take_bash_from_the_current_folder(self):
        self.program("bash.exe" if os.name == "nt" else "bash")
        self.program("bin/bash.exe" if os.name == "nt" else "bin/bash")
        original_cwd = os.getcwd()
        try:
            os.chdir(self.root)
            for path in ("", ".", "bin"):
                with self.subTest(path=path), patch.dict(os.environ, PATH=path):
                    with self.assertRaises(LadderError) as raised:
                        self.runner._argv(["bash"])
                    self.assertEqual(str(raised.exception), "bash: not found")
        finally:
            os.chdir(original_cwd)

    def test_relative_override_is_resolved_before_switching_to_project_folder(self):
        bash = self.program("custom/bash.exe")
        original_cwd = os.getcwd()
        try:
            os.chdir(self.root)
            os.environ["LADDER_BASH"] = "custom/bash.exe"
            self.assertEqual(self.runner._argv(["bash"], cwd=str(self.root / "project")),
                             [str(bash)])
        finally:
            os.chdir(original_cwd)

    def test_shell_task_passes_selected_bash_and_project_folder_to_child(self):
        bash = self.program("Git/bin/bash.exe")
        git = self.program("Git/cmd/" + ("git.exe" if os.name == "nt" else "git"))
        self.on_path(git.parent)
        project = parse('[tasks.check]\nabout = "Check"\nrun = "echo hi | cat"\nshell = "bash"',
                        str(self.root / "project" / "ladder.toml"))
        out, err = io.StringIO(), io.StringIO()
        with patch("ladder.process.WINDOWS", True), patch("subprocess.Popen") as popen:
            child = popen.return_value.__enter__.return_value
            child.stdout = iter(["checked\n"])
            child.wait.return_value = 0
            code = main(["check"], Context(Runner(out), out, err,
                                         load_config=lambda _: project))
            self.assertEqual(popen.call_args.args[0], [str(bash), "-c", "echo hi | cat"])
            self.assertEqual(popen.call_args.kwargs["cwd"], str(self.root / "project"))
        self.assertEqual((code, err.getvalue()), (0, f"ladder: using {project.path}\n"))
        self.assertTrue(out.getvalue().endswith("checked\n"))
