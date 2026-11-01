import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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
