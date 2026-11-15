"""Run ladder with stdout reporting a terminal, even through a pipe."""

import io
import runpy
import sys


class TTYStdout(io.TextIOWrapper):
    def isatty(self):
        return True


def main():
    stdout = sys.stdout
    stdout.flush()
    sys.stdout = TTYStdout(stdout.buffer, encoding=stdout.encoding,
                          errors=stdout.errors, line_buffering=stdout.line_buffering)
    sys.argv = ["ladder", *sys.argv[1:]]
    runpy.run_module("ladder", run_name="__main__")


if __name__ == "__main__":
    main()
