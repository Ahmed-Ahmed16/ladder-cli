import os
import re
import shlex
import shutil
import subprocess
import unicodedata


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


class Runner:
    def __init__(self, out):
        self.out = out

    def _argv(self, argv, cwd=None):
        print("$ " + redact(shlex.join(argv)).replace("\n", "\\n"), file=self.out, flush=True)
        if "/" in argv[0] or "\\" in argv[0]:
            program = os.path.abspath(os.path.join(cwd or os.getcwd(), argv[0]))
            if not os.path.isfile(program):
                raise LadderError(f"{plain(argv[0])}: not found")
            return [program, *argv[1:]]
        directories = [directory for directory in os.environ.get("PATH", "").split(os.pathsep)
                       if os.path.isabs(directory)
                       and (os.name != "nt" or os.path.splitdrive(directory)[0])]
        search_path = os.pathsep.join(directories)
        program = None
        for directory in directories:
            # A full candidate path prevents Windows from prepending the current folder.
            program = shutil.which(os.path.join(directory, argv[0]), path=search_path)
            if program is not None:
                break
        if program is not None:
            folder = os.path.normcase(os.path.realpath(os.path.dirname(program)))
            allowed = {os.path.normcase(os.path.realpath(directory)) for directory in directories}
            if folder == os.path.normcase(os.path.realpath(os.getcwd())) and folder not in allowed:
                program = None
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
