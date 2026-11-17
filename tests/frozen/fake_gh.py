"""Serve frozen gh replies without a service connection.

FAKE_GH_STATE names a JSON file with id and calls. Each call has match
(an argument prefix), exit, stdout and stderr. The longest prefix wins.
Field lists after --json do not change replies. --jq and -q are unsupported.
Their validation precedes state dispatch, including the outage state.
"""

import json
import os
import sys


def emit(call):
    sys.stdout.write(call["stdout"])
    sys.stderr.write(call["stderr"])
    return call["exit"]


def main(argv):
    try:
        with open(os.environ["FAKE_GH_STATE"], encoding="utf-8") as stream:
            state = json.load(stream)
        if set(state) != {"id", "calls"} or not isinstance(state["id"], str):
            raise ValueError("invalid state")
        if not isinstance(state["calls"], list):
            raise ValueError("invalid calls")
        for call in state["calls"]:
            if (set(call) != {"match", "exit", "stdout", "stderr"}
                    or not isinstance(call["match"], list)
                    or not all(isinstance(arg, str) for arg in call["match"])
                    or type(call["exit"]) is not int
                    or not isinstance(call["stdout"], str)
                    or not isinstance(call["stderr"], str)):
                raise ValueError("invalid call")
    except (OSError, KeyError, TypeError, ValueError):
        sys.stderr.write("fake gh: invalid FAKE_GH_STATE\n")
        return 1
    matches = [call for call in state["calls"]
               if argv[:len(call["match"])] == call["match"]]
    best = max(matches, key=lambda call: len(call["match"]), default=None)
    if any(arg == "--jq" or arg.startswith(("--jq=", "-q"))
           for arg in argv):
        sys.stderr.write("fake gh: --jq not supported; read the JSON yourself\n")
        return 2
    if best is not None:
        return emit(best)
    if argv == ["--version"]:
        sys.stdout.write("gh version 0.0.0 (fake)\n")
        return 0
    if argv[:2] == ["auth", "status"]:
        return 0
    sys.stderr.write("fake gh: no stub for " + " ".join(argv[:3]) + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
