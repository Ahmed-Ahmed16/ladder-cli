from pathlib import Path

from .process import LadderError, plain, redact, split_command


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
    for step, line in enumerate(lines, 1):
        if args.dry_run:
            print(f"{step}: {redact(line)}", file=out)
            continue
        label = f"step {step} of {len(lines)}: {redact(line)}"
        try:
            argv = split_command(line, f"gate step {step}")
            code = runner.stream(argv, cwd=str(Path(project.path).parent))
        except LadderError:
            print(f"FAIL {label} (exit 1)", file=out)
            raise
        if code:
            print(f"FAIL {label} (exit {code})", file=out)
            return code
        print(f"PASS {label}", file=out)
    if not args.dry_run:
        print(f"gates: all {len(lines)} passed", file=out)
    return 0
