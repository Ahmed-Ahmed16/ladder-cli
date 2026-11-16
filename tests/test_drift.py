import argparse
from importlib.resources import files
import io
from pathlib import Path
import re
import unittest

from ladder.cli import Context, arguments, main
from ladder.config import CORE_JOBS
from tests.test_cli import FakeRunner


# These are examples or placeholders, not additional built-in commands.
TASK_EXAMPLES = {
    "<task>": "A project task supplied by ladder.toml.",
    "<name>": "The task name created by the preceding ladder add example.",
    "<job>": "A placeholder for a job whose --help is requested.",
    "NAME": "The task name supplied to ladder add in README.md.",
    "test": "The sample task defined in both documents' TOML examples.",
}


def children(parser):
    return {name: child for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
            for name, child in action.choices.items()}


def walk_parsers(parser, path=()):
    yield path, parser
    for name, child in children(parser).items():
        yield from walk_parsers(child, (*path, name))


def documented_commands(text):
    snippets = re.finditer(r"`{3}[^\n]*\n(?P<block>.*?)`{3}|`(?P<inline>[^`\n]+)`", text, re.S)
    command = re.compile(
        r"(?<![\w./-])ladder[ \t]+(?:--human[ \t]+)?"
        r"(?P<job><[^>\n]+>|\w[\w-]*)"
        r"(?:[ \t]+(?P<subcommand><[^>\n]+>|\w[\w-]*))?")
    for snippet in snippets:
        for match in command.finditer(snippet.group("block") or snippet.group("inline") or ""):
            yield match.group("job"), match.group("subcommand")


class DriftTests(unittest.TestCase):
    def setUp(self):
        self.parser = arguments()
        self.jobs = children(self.parser)
        self.pr_commands = children(self.jobs["pr"])
        self.skill = files("ladder").joinpath("skill/SKILL.md").read_text(encoding="utf-8")
        self.readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")

    def help_for(self, path):
        out, err = io.StringIO(), io.StringIO()
        context = Context(FakeRunner(out), out, err,
                          load_config=lambda _: self.fail("help read project config"))
        self.assertEqual(main([*path, "--help"], context), 0)
        self.assertEqual(err.getvalue(), "")
        return " ".join(out.getvalue().split())

    def assert_word(self, word, text):
        self.assertRegex(text, rf"(?<![\w-]){re.escape(word)}(?![\w-])")

    def test_description_comes_from_jobs_and_pr_subcommands(self):
        self.assertEqual(set(self.jobs), set(CORE_JOBS))
        expected = [*self.jobs, *(f"pr {name}" for name in self.pr_commands), "<task> [args]"]
        self.assertEqual(self.parser.description.split(" | "), expected)

    def test_jobs_and_pr_subcommands_appear_in_help_and_skill(self):
        top_help = self.help_for(())
        for name in self.jobs:
            with self.subTest(job=name):
                self.assert_word(name, top_help)
                self.assert_word(name, self.skill)
        for name in self.pr_commands:
            with self.subTest(pr=name):
                command = f"pr {name}"
                self.assertIn(command, top_help)
                self.assertIn(command, self.help_for(("pr", name)))
                self.assertIn(command, self.skill)

    def test_each_long_flag_appears_in_its_own_help_and_skill(self):
        for path, parser in walk_parsers(self.parser):
            help_text = self.help_for(path)
            flags = sorted({flag for action in parser._actions
                            for flag in action.option_strings if flag.startswith("--")})
            for flag in flags:
                with self.subTest(parser=path, flag=flag):
                    self.assert_word(flag, help_text)
                    self.assert_word(flag, self.skill)

    def test_documented_commands_are_real_or_named_task_examples(self):
        for name, text in (("SKILL.md", self.skill), ("README.md", self.readme)):
            commands = list(documented_commands(text))
            self.assertTrue(commands, name)
            for job, subcommand in commands:
                with self.subTest(document=name, job=job, subcommand=subcommand):
                    if job in TASK_EXAMPLES:
                        continue
                    self.assertIn(job, self.jobs)
                    if job == "pr":
                        self.assertIn(subcommand, self.pr_commands)

    def test_scanner_reads_code_and_skips_prose_and_output(self):
        text = ("Prose: ladder typo.\n"
                "`ladder missing` and `ladder pr missing`\n"
                "```console\nladder --human gates\nladder list\n```\n"
                "`ladder: FAIL test`")
        self.assertEqual(list(documented_commands(text)),
                         [("missing", None), ("pr", "missing"), ("gates", None), ("list", None)])
