import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ladder.cli import main
from ladder.config import load, parse
from tests.test_cli import FakeRunner


class SetupCase:
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "home"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.child = self.repo / "child"
        self.child.mkdir()

    def invoke(self, *argv, start=None):
        out, err = io.StringIO(), io.StringIO()
        with patch("os.getcwd", return_value=str(start or self.child)):
            code = main(list(argv), FakeRunner(out), out, err, home=self.home)
        return code, out.getvalue(), err.getvalue()


class InitCliTests(SetupCase, unittest.TestCase):
    def test_init_from_subfolder_writes_parseable_root_config_and_prints_guidance(self):
        for git_directory in (True, False):
            with self.subTest(git_directory=git_directory):
                marker = self.repo / ".git"
                marker.mkdir() if git_directory else marker.touch()
                code, out, err = self.invoke("init")
                self.assertEqual((code, err), (0, ""))
                project = load(self.child)
                self.assertEqual(project.path, str(self.repo / "ladder.toml"))
                self.assertEqual(project.tasks, {})
                self.assertEqual(project.gates["run"], ("git --version",))
                text = Path(project.path).read_text(encoding="utf-8")
                self.assertIn("CI", text)
                example = "\n".join(line[2:] for line in text.split("\n\n")[0].splitlines())
                # The commented task must also work when the user enables it.
                self.assertEqual(parse(example, "example").tasks["test"].run,
                                 ("python -m unittest discover -s tests -t .",))
                self.assertEqual(out, "This repo uses ladder for repeated jobs.\n"
                                 "Run `ladder list` before writing any script; tasks live in ladder.toml.\n")
                self.assertFalse((self.repo / "AGENTS.md").exists())
                Path(project.path).unlink()
                marker.rmdir() if git_directory else marker.unlink()

    def test_init_refuses_existing_file_without_changing_bytes(self):
        (self.repo / ".git").mkdir()
        path = self.repo / "ladder.toml"
        original = b"existing\r\n\xff"
        path.write_bytes(original)
        self.assertEqual(self.invoke("init"),
                         (1, "", "ladder: ladder.toml already exists; edit it instead\n"))
        self.assertEqual(path.read_bytes(), original)

    def test_init_outside_repo_refuses_even_with_parent_config(self):
        (self.root / "ladder.toml").touch()
        self.assertEqual(self.invoke("init"),
                         (1, "", "ladder: not in a git repo\n"))
        self.assertFalse((self.repo / "ladder.toml").exists())


class InstallSkillTests(SetupCase, unittest.TestCase):
    def targets(self):
        return [self.home / ".claude/skills/ladder/SKILL.md",
                self.home / ".agents/skills/ladder/SKILL.md",
                self.home / ".codex/AGENTS.md"]

    def test_install_writes_packaged_page_and_rerun_changes_nothing(self):
        from importlib.resources import files

        code, out, err = self.invoke("install-skill")
        self.assertEqual((code, err), (0, ""))
        paths = self.targets()
        self.assertEqual(out.splitlines(), [f"wrote {path}" for path in paths])
        page = files("ladder").joinpath("skill/SKILL.md").read_bytes()
        self.assertEqual(paths[0].read_bytes(), page)
        self.assertEqual(paths[1].read_bytes(), page)
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        self.assertEqual(self.invoke("install-skill"),
                         (0, "".join(f"unchanged {path}\n" for path in paths), ""))
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in paths], before)
        self.assertEqual(paths[2].read_bytes().count(b"<!-- ladder:start -->"), 1)

    def test_install_replaces_old_page_and_only_marked_text(self):
        paths = self.targets()
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        paths[0].write_bytes(b"old page")
        paths[1].write_bytes(b"old page")
        prefix = b"\xef\xbb\xbfHuman rules\r\n\xff\r\n<!-- ladder:start -->\r\n"
        suffix = b"<!-- ladder:end -->\r\nKeep this\n\xfe"
        paths[2].write_bytes(prefix + b"old rule\r\n" + suffix)
        code, out, err = self.invoke("install-skill")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [f"updated {path}" for path in paths])
        written = paths[2].read_bytes()
        self.assertTrue(written.startswith(prefix))
        self.assertTrue(written.endswith(suffix))
        self.assertIn(b"ladder list", written)
        self.assertNotIn(b"old rule", written)
        self.assertEqual(self.invoke("install-skill"),
                         (0, "".join(f"unchanged {path}\n" for path in paths), ""))

    def test_failed_replace_preserves_original_and_removes_temporary_file(self):
        path = self.targets()[0]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"keep page")
        replacements = []

        def denied(source, destination):
            replacements.append((source.parent, destination))
            self.assertEqual(path.read_bytes(), b"keep page")
            self.assertNotEqual(source.read_bytes(), b"keep page")
            raise PermissionError("replace denied")

        with patch("ladder.setup.os.replace", denied):
            code, out, err = self.invoke("install-skill")
        self.assertEqual((code, out, err), (1, "", "ladder: replace denied\n"))
        self.assertEqual(replacements, [(path.parent, path)])
        self.assertEqual(path.read_bytes(), b"keep page")
        self.assertEqual(list(path.parent.iterdir()), [path])
        self.assertFalse(self.targets()[2].exists())

    def test_missing_markers_append_after_blank_line_preserving_existing_bytes(self):
        path = self.targets()[2]
        path.parent.mkdir(parents=True)
        # Cases: empty, no final newline, LF, CRLF, existing blank line.
        for original, separator in ((b"", b""), (b"rules", b"\n\n"),
                                    (b"rules\n", b"\n"), (b"rules\r\n", b"\r\n"),
                                    (b"rules\n\n", b"")):
            with self.subTest(original=original):
                path.write_bytes(original)
                code, _, err = self.invoke("install-skill")
                self.assertEqual((code, err), (0, ""))
                self.assertTrue(path.read_bytes().startswith(original + separator + b"<!-- ladder:start -->"))

    def test_broken_markers_refuse_before_any_file_changes(self):
        start, end = b"<!-- ladder:start -->\n", b"<!-- ladder:end -->\n"
        # Cases: each missing marker, duplicates, reversed markers.
        for original in (start, end, start + start + end, start + end + end, end + start):
            for installed in (False, True):
                with self.subTest(original=original, installed=installed):
                    paths = self.targets()
                    for path in paths:
                        path.parent.mkdir(parents=True, exist_ok=True)
                    for path in paths[:2]:
                        if installed:
                            path.write_bytes(b"keep page")
                        else:
                            path.unlink(missing_ok=True)
                    paths[2].write_bytes(original)
                    code, out, err = self.invoke("install-skill")
                    self.assertEqual((code, out), (1, ""))
                    self.assertIn("invalid ladder markers", err)
                    self.assertEqual(len(err.splitlines()), 1)
                    self.assertEqual(paths[2].read_bytes(), original)
                    for path in paths[:2]:
                        if installed:
                            self.assertEqual(path.read_bytes(), b"keep page")
                        else:
                            self.assertFalse(path.exists())
