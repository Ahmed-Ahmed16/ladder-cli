from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ladder.config import Config, find, load
from ladder.process import LadderError


class ConfigFileTests(unittest.TestCase):
    def test_nearest_file_wins_including_at_git_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            child = root / "child"
            child.mkdir()
            (root / ".git").mkdir()
            (root / "ladder.toml").touch()
            self.assertEqual(find(str(child)), str(root / "ladder.toml"))
            (child / "ladder.toml").touch()
            self.assertEqual(find(str(child)), str(child / "ladder.toml"))

    def test_search_stops_at_git_directory_or_worktree_file(self):
        for git_directory in (True, False):
            with self.subTest(git_directory=git_directory), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                child = root / "repo"
                child.mkdir()
                marker = child / ".git"
                marker.mkdir() if git_directory else marker.touch()
                (root / "ladder.toml").touch()
                self.assertIsNone(find(str(child)))
                self.assertIsNone(load(str(child)))

    def test_search_stops_at_filesystem_root(self):
        with patch("ladder.config.Path.is_file", return_value=False):
            with patch("ladder.config.Path.exists", return_value=False):
                self.assertIsNone(find(Path.cwd().anchor))

    def test_load_reads_utf8_and_passes_text_and_path_to_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "ladder.toml"
            text = '# caf\u00e9\n'
            path.write_text(text, encoding="utf-8")
            expected = Config(str(path), {}, {}, {})
            # Check the file input separately from parsing its contents.
            def parser(received_text, received_path):
                self.assertEqual((received_text, received_path), (text, str(path)))
                return expected

            with patch("ladder.config.parse", parser):
                self.assertEqual(load(directory), expected)

    def test_load_parses_tasks_from_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "ladder.toml"
            path.write_text('[tasks.test]\nabout = "Run tests"\nrun = "python tests.py"',
                            encoding="utf-8")
            config = load(directory)
            self.assertEqual(config.path, str(path))
            self.assertEqual(config.tasks["test"].run, ("python tests.py",))

    def test_unreadable_or_invalid_utf8_file_names_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "ladder.toml"
            path.write_bytes(b"\xff")
            for error in (None, PermissionError("denied")):
                with self.subTest(error=error):
                    if error is None:
                        with self.assertRaises(LadderError) as raised:
                            load(directory)
                    else:
                        with patch("ladder.config.Path.read_text", side_effect=error):
                            with self.assertRaises(LadderError) as raised:
                                load(directory)
                    self.assertTrue(str(raised.exception).startswith(str(path) + ": could not read: "))
