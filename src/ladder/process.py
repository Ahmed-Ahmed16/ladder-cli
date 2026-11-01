import re
import shlex
import shutil
import subprocess


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
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", message)


def plain(message):
    return " ".join(redact(message).split())


class Runner:
    def __init__(self, out):
        self.out = out

    def _argv(self, argv):
        print("$ " + redact(shlex.join(argv)).replace("\n", "\\n"), file=self.out, flush=True)
        program = shutil.which(argv[0])
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

    def stream(self, argv) -> int:
        command = self._argv(argv)
        try:
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace") as child:
                for line in child.stdout:
                    print(redact(line), file=self.out, end="", flush=True)
                return child.wait()
        except OSError as error:
            raise LadderError(f"could not start {plain(argv[0])}: {plain(str(error))}") from error
