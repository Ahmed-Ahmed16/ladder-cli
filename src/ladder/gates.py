from pathlib import Path

from .process import LadderError, StepTimeout, TIMEOUT_EXIT, plain, redact, split_command
from .runlog import logged, summary


def warn_ci(project, err):
    ci = project.gates.get("ci")
    if ci is None:
        return
    try:
        text = (Path(project.path).parent / ci).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"warning: could not read {plain(ci)}: {plain(str(error))}", file=err)
        return
    normalized = " ".join(text.split())
    for step, line in enumerate(project.gates["run"], 1):
        if " ".join(line.split()) not in normalized:
            print(f"warning: gate step {step} not found in {plain(ci)}: {redact(line)}", file=err)


def run_gates(args, project, runner, out):
    lines = project.gates["run"]
    if args.dry_run:
        for step, line in enumerate(lines, 1):
            print(f"{step}: {redact(line)}", file=out)
        return 0
    with logged(runner, out, "gates") as (tee, path):
        for step, line in enumerate(lines, 1):
            label = f"step {step} of {len(lines)}: {redact(line)}"
            try:
                argv = split_command(line, f"gate step {step}")
                code = runner.stream(argv, cwd=str(Path(project.path).parent))
            except StepTimeout as error:
                summary(tee, f"FAIL {label} (timeout after {error.seconds:g}s, exit {TIMEOUT_EXIT}); full log: {path}")
                return TIMEOUT_EXIT
            except LadderError:
                summary(tee, f"FAIL {label} (exit 1); full log: {path}")
                raise
            if code:
                summary(tee, f"FAIL {label} (exit {code}); full log: {path}")
                return code
            print(f"PASS {label}", file=tee)
        summary(tee, f"gates: all {len(lines)} passed; full log: {path}")
    return 0
