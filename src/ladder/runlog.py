from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from .cap import Capped
from .process import LadderError, redact


def private_folder():
    directory = Path(tempfile.gettempdir()) / "ladder" / "logs"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if hasattr(os, "getuid"):
        status = directory.lstat()
        if stat.S_ISLNK(status.st_mode) or status.st_uid != os.getuid() or status.st_mode & 0o077:
            raise LadderError(f"{directory}: must be a private folder owned by you")
    return directory


def create_log(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8", errors="replace", newline="\n")


class Tee:
    def __init__(self, out, log, path=None):
        self.out = out
        self.log = log
        self.path = path
        self.line_start = True

    def write(self, text):
        self.out.write(text)
        self.log.write(redact(text))
        if text:
            self.line_start = text.endswith("\n")
        return len(text)

    def finish(self):
        if isinstance(self.out, Capped):
            self.out.finish(self.path)

    def flush(self):
        self.out.flush()
        self.log.flush()


def summary(tee, message):
    if not tee.line_start:
        print(file=tee)
    tee.finish()
    print(message, file=tee, flush=True)


def open_log(name):
    directory = private_folder()
    name = re.sub(r"[^\w.-]", "_", name)
    stem = f"{name}-{time.strftime('%Y%m%d-%H%M%S')}"
    number = 1
    while True:
        suffix = f"-{number}" if number > 1 else ""
        path = directory / f"{stem}{suffix}.log"
        try:
            log = create_log(path)
            return log, path
        except FileExistsError:
            number += 1


@contextmanager
def logged(runner, out, name, agent=False):
    log, path = open_log(name)
    with log:
        tee = Tee(Capped(out) if agent else out, log, path)
        previous = runner.out
        runner.out = tee
        try:
            yield tee, path
        finally:
            runner.out = previous
            tee.finish()
