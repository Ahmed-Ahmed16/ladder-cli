import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import unicodedata


WINDOWS = os.name == "nt"


class LadderError(Exception):
    pass


def redact(message):
    secret_value = r'''(?:"(?:\\.|[^"\\])*(?:"|$)|'(?:\\.|[^'\\])*(?:'|$)|[^\s,;}]+)'''
    message = re.sub(r"\b(?:gh[pousr]_[\w]+|github_pat_[\w]+|glpat-[\w-]+|sk-[\w-]+)\b",
                     "[redacted]", message)
    message = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [redacted]", message)
    message = re.sub(r"(?i)(--(?:token|password|secret|api[_-]?key)\s+)" + secret_value,
                     r"\1[redacted]", message)
    message = re.sub(r'''(?i)(["']?\b(?:token|password|secret|api[_-]?key)["']?\s*[:=]\s*)''' + secret_value,
                     r"\1[redacted]", message)
    return "".join(char for char in message
                   if char in "\n\t" or not unicodedata.category(char).startswith("C"))


def plain(message):
    return " ".join(redact(message).split())


def split_command(line, label):
    try:
        argv = shlex.split(line, posix=True)
    except ValueError as error:
        raise LadderError(f"{label}: {error}") from error
    if not argv or not argv[0]:
        raise LadderError(f"{label}: run must name a program")
    return argv


def path_program(name):
    directories = [directory for directory in os.environ.get("PATH", "").split(os.pathsep)
                   if os.path.isabs(directory)
                   and (os.name != "nt" or os.path.splitdrive(directory)[0])]
    search_path = os.pathsep.join(directories)
    for directory in directories:
        # A full candidate path prevents Windows from prepending the current folder.
        program = shutil.which(os.path.join(directory, name), path=search_path)
        if program is not None:
            return program
    return None


def git_bash():
    git = path_program("git")
    if git is None:
        return None
    folder = Path(git).parent
    if folder.name.lower() == "bin" and folder.parent.name.lower() == "mingw64":
        root = folder.parent.parent
    elif folder.name.lower() in ("cmd", "bin"):
        root = folder.parent
    else:
        return None
    candidate = root / "bin" / "bash.exe"
    return str(candidate) if candidate.is_file() else None


def bash_program():
    override = os.environ.get("LADDER_BASH")
    if override is not None:
        if not os.path.isfile(override):
            raise LadderError(f"LADDER_BASH: file not found: {plain(override)}")
        return os.path.abspath(override)
    if WINDOWS and (candidate := git_bash()) is not None:
        return candidate
    program = path_program("bash")
    if program is None:
        raise LadderError("bash: not found")
    if WINDOWS:
        system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        resolved = Path(program).resolve()
        if system32.resolve() in resolved.parents or any(part.lower() == "windowsapps" for part in resolved.parts):
            raise LadderError("bash: only WSL bash found; install Git for Windows or set LADDER_BASH")
    return program


class Runner:
    def __init__(self, out):
        self.out = out

    def _argv(self, argv, cwd=None):
        print("$ " + redact(shlex.join(argv)).replace("\n", "\\n"), file=self.out, flush=True)
        if argv[0] == "bash":
            return [bash_program(), *argv[1:]]
        if "/" in argv[0] or "\\" in argv[0]:
            program = os.path.abspath(os.path.join(cwd or os.getcwd(), argv[0]))
            if not os.path.isfile(program):
                raise LadderError(f"{plain(argv[0])}: not found")
            return [program, *argv[1:]]
        program = path_program(argv[0])
        if program is None:
            raise LadderError(f"{plain(argv[0])}: not found")
        return [program, *argv[1:]]

    def _capture(self, argv):
        command = self._argv(argv)
        try:
            return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        except OSError as error:
            raise LadderError(f"could not start {plain(argv[0])}: {plain(str(error))}") from error

    def capture(self, argv) -> str:
        captured = self._capture(argv)
        if captured.returncode:
            tail = plain(redact(captured.stderr)[-1000:])
            raise LadderError(f"{plain(argv[0])}: exit {captured.returncode}: {tail or 'no error output'}")
        return captured.stdout

    def check(self, argv) -> tuple[int, str]:
        captured = self._capture(argv)
        return captured.returncode, captured.stdout

    def stream(self, argv, cwd=None) -> int:
        command = self._argv(argv, cwd)
        try:
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace", cwd=cwd) as child:
                for line in child.stdout:
                    print(redact(line), file=self.out, end="", flush=True)
                return child.wait()
        except OSError as error:
            raise LadderError(f"could not start {plain(argv[0])}: {plain(str(error))}") from error
