import re
import tomllib

from .config import parse, repo_root
from .process import LadderError, plain
from .setup import atomic_write, read_existing


def toml_string(text):
    escaped = []
    for char in text:
        if char in ('\\', '"'):
            escaped.append('\\' + char)
        elif ord(char) < 32 or ord(char) == 127:
            escaped.append(f"\\u{ord(char):04x}")
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


def task_block(args):
    runs = [toml_string(line) for line in args.run]
    run = runs[0] if len(runs) == 1 else "[" + ", ".join(runs) + "]"
    lines = [f"[tasks.{args.name}]", f"about = {toml_string(args.about)}", f"run = {run}"]
    if args.shell is not None:
        lines.append(f"shell = {toml_string(args.shell)}")
    if args.confirm:
        lines.append("confirm = true")
    return "\n".join(lines) + "\n"


def validate_addition(content, original, name, path):
    try:
        parse(content.decode("utf-8"), str(path))
    except LadderError as error:
        # Schema errors in the old task must not hide the duplicate message.
        try:
            tasks = tomllib.loads(original.decode("utf-8") if original is not None else "").get("tasks", {})
        except tomllib.TOMLDecodeError:
            raise error
        if isinstance(tasks, dict) and name in tasks:
            raise LadderError(f'task "{name}" already exists; edit its script instead') from error
        raise


def add_task(start, args, out):
    root = repo_root(start)
    if root is None:
        raise LadderError("not in a git repo")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        raise LadderError("name must contain only letters, digits, - and _")
    path = root / "ladder.toml"
    original = read_existing(path)
    block = task_block(args).encode("utf-8")
    # Keep original bytes, including line endings and comments, out of text I/O.
    separator = b"" if original is None else (b"\n" if original.endswith(b"\n") else b"\n\n")
    content = (original if original is not None else b"") + separator + block
    validate_addition(content, original, args.name, path)
    atomic_write(path, content)
    print(f'added task "{args.name}" to {plain(str(path))}', file=out)
    print(f"run it once: ladder {args.name}", file=out)
