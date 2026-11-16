import os
from pathlib import Path
import re
import stat

from . import runlog
from .process import LadderError, plain, redact


def add_arguments(parser, positive):
    parser.add_argument("log", help="private log path, file name, or task name")
    parser.add_argument("--grep", metavar="RE", help="select lines with a regular expression")
    parser.add_argument("--head", type=positive, metavar="N", help="first N selected lines")
    parser.add_argument("--tail", type=positive, metavar="N", help="last N selected lines")
    parser.add_argument("--max-chars", type=positive, default=4000, metavar="N",
                        help="maximum log text characters (default: 4000)")


def find_log(log, directory):
    path = Path(log)
    if path.is_absolute():
        return path
    if path.name != log:
        raise LadderError(f"{log}: not a ladder log")
    name = path.stem if path.suffix == ".log" else log
    matches = [entry for entry in directory.iterdir()
               if entry.suffix == ".log"
               and (entry.name == name + ".log" or entry.name.startswith(name + "-"))]
    if not matches:
        raise LadderError(f"no log found for {log}")
    return max(matches, key=lambda entry: (entry.lstat().st_mtime_ns, entry.name))


def checked_log(log, directory):
    path = find_log(log, directory)
    if path.suffix != ".log" or path.parent.resolve() != directory:
        raise LadderError(f"{log}: not a ladder log")
    path = directory / path.name
    status = path.lstat()
    if not stat.S_ISREG(status.st_mode):
        raise LadderError(f"{log}: not a ladder log")
    return path, status


def read_log(log):
    try:
        directory = runlog.private_folder().resolve()
        path, expected = checked_log(log, directory)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, encoding="utf-8", errors="replace") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode)
                    or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)):
                raise LadderError(f"{log}: not a ladder log")
            return path, stream.read().splitlines()
    except FileNotFoundError as error:
        raise LadderError(f"no log found for {log}") from error
    except OSError as error:
        raise LadderError(f"{log}: not a ladder log") from error


def pattern_for(expression):
    try:
        return re.compile(expression) if expression is not None else None
    except re.error as error:
        raise LadderError(f"invalid --grep regex: {error.msg}") from error


def short_line(line):
    return line if len(line) <= 300 else line[:297] + "..."


def limit_lines(lines, maximum):
    body = "\n".join(lines)
    if len(body) <= maximum:
        return lines, []
    prefix = body[:maximum]
    if "\n" in prefix:
        prefix = prefix.rsplit("\n", 1)[0]
    return prefix.split("\n"), [f"(cut at {maximum} chars)"]


def log_job(args, context):
    if args.head is not None and args.tail is not None:
        raise LadderError("--head and --tail cannot be used together")
    pattern = pattern_for(args.grep)
    path, lines = read_log(args.log)
    selected = [line for line in lines if pattern is None or pattern.search(line)]
    no_matches = pattern is not None and not selected
    selected = selected[:args.head] if args.head is not None else selected[-(args.tail or 40):]
    selected, marker = limit_lines([short_line(redact(line)) for line in selected], args.max_chars)
    header = f"showing {len(selected)} of {len(lines)} lines in {plain(path.name)}"
    message = [header, "no lines match"] if no_matches else [header, *selected, *marker]
    print(redact("\n".join(message)), file=context.out)
    return 1 if no_matches else 0
