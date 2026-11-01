import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ladder.process import LadderError, Runner


class RunnerTests(unittest.TestCase):
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
