from importlib.resources import files
import os
from pathlib import Path
import tempfile

from .config import repo_root
from .process import LadderError


START = b"<!-- ladder:start -->"
END = b"<!-- ladder:end -->"
GUIDANCE = (
    "Before writing any script, run `ladder list` in the repo. If a task exists, use it.",
    "If a task is broken or outdated, fix its script in place. Never write a second script for the same job.",
    "A script used once may stay in a temp folder. Save a script the job will need again in `scripts/ladder/` in the repo.",
    'Add it with `ladder add <name> --about "..." --run "..."`. Never hand edit ladder.toml to add a task.',
    "Run it once with `ladder <name>` to prove it works. Put the script and ladder.toml change in the same commit as the work.",
    "In company repos, the task reaches Ahmed through the same PR. Never put a path outside the repo in its ladder.toml.",
    "Personal scripts get tasks in their own folder's ladder.toml. Read `ladder help` for arguments.",
)
STARTER = '''# [tasks.test]
# about = "Run the tests"
# run = "python -m unittest discover -s tests -t ."

[gates]
# Replace this with the CI steps for this repo.
run = ["git --version"]
'''


def init(start, out):
    root = repo_root(start)
    if root is None:
        raise LadderError("not in a git repo")
    try:
        with (root / "ladder.toml").open("x", encoding="utf-8", newline="\n") as target:
            target.write(STARTER)
    except FileExistsError as error:
        raise LadderError("ladder.toml already exists; edit it instead") from error
    print("This repo uses ladder for repeated jobs.", file=out)
    print("Run `ladder list` before writing any script; save reusable scripts in "
          "scripts/ladder/ and use `ladder add` to add tasks.", file=out)


def read_existing(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def agents_section(original):
    # Exact marker lines only; preserve every byte outside their contents.
    lines = original.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n") == START]
    ends = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n") == END]
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    body = newline.join(line.encode("utf-8") for line in GUIDANCE) + newline
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            raise LadderError("AGENTS.md: invalid ladder markers; expected 1 start then 1 end")
        return b"".join(lines[:starts[0] + 1]) + body + b"".join(lines[ends[0]:])
    separator = b""
    if original and not original.endswith(newline * 2):
        separator = newline if original.endswith(newline) else newline * 2
    return original + separator + START + newline + body + END + newline


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
            temporary = Path(target.name)
            target.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_skill(out, home=None):
    home = Path.home() if home is None else Path(home)
    agents = home / ".codex" / "AGENTS.md"
    original_agents = read_existing(agents)
    section = agents_section(original_agents if original_agents is not None else b"")
    page = files("ladder").joinpath("skill/SKILL.md").read_bytes()
    planned = [(home / folder / "skills" / "ladder" / "SKILL.md", page)
               for folder in (".claude", ".agents")]
    planned.append((agents, section))
    for path, content in planned:
        original = original_agents if path == agents else read_existing(path)
        status = "unchanged"
        if original != content:
            atomic_write(path, content)
            status = "wrote" if original is None else "updated"
        print(f"{status} {path}", file=out)
