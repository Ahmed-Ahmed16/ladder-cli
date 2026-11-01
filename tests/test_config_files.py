from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ladder.config import find, load
from ladder.process import LadderError


class ConfigFileTests(unittest.TestCase):
    def test_only_repo_root_file_is_used_from_root_or_subfolder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            child = root / "child"
            child.mkdir()
            (root / ".git").mkdir()
            (root / "ladder.toml").touch()
            self.assertEqual(find(str(root)), str(root / "ladder.toml"))
            self.assertEqual(find(str(child)), str(root / "ladder.toml"))
            (child / "ladder.toml").touch()
            self.assertEqual(find(str(child)), str(root / "ladder.toml"))
            (root / "ladder.toml").unlink()
            self.assertIsNone(find(str(child)))

    def test_outside_repo_ignores_planted_parent_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            child.mkdir()
            (root / "ladder.toml").write_text('[tasks.planted]\nabout = "Planted"\nrun = "bad"')
            self.assertIsNone(find(str(child)))
            self.assertIsNone(load(str(child)))

    def test_nearest_repo_wins_with_git_file_or_folder(self):
        for git_directory in (True, False):
            with self.subTest(git_directory=git_directory), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / ".git").mkdir()
                (root / "ladder.toml").touch()
                nested = root / "nested"
                nested.mkdir()
                marker = nested / ".git"
                marker.mkdir() if git_directory else marker.touch()
                (nested / "ladder.toml").touch()
                self.assertEqual(find(str(nested)), str(nested / "ladder.toml"))

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

    def test_load_parses_tasks_from_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "ladder.toml"
            (path.parent / ".git").mkdir()
            path.write_text('[tasks.test]\nabout = "Run caf\u00e9 tests"\nrun = "python tests.py"',
                            encoding="utf-8")
            config = load(directory)
            self.assertEqual(config.path, str(path))
            self.assertEqual(config.tasks["test"].about, "Run caf\u00e9 tests")
            self.assertEqual(config.tasks["test"].run, ("python tests.py",))

    def test_unreadable_or_invalid_utf8_file_names_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "ladder.toml"
            (path.parent / ".git").mkdir()
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
