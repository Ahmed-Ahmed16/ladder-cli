from pathlib import Path
import shlex

from .process import LadderError, StepTimeout, TIMEOUT_EXIT, plain, split_command
from .runlog import logged, summary


def command(task, line, extra):
    if task.shell == "bash":
        return ["bash", "-o", "pipefail", "-c", line + (" " + shlex.join(extra) if extra else "")]
    return [*split_command(line, f'task "{task.name}"'), *extra]


def run_task(config, argv, runner, out, err):
    name, *extra = argv
    task = config.tasks.get(name) if config is not None else None
    if task is None:
        raise LadderError(f'unknown job or task "{name}"; run ladder list')
    if task.confirm and "--yes" not in extra:
        raise LadderError(f'task "{name}" needs --yes')
    if len(task.run) > 1:
        extra = [arg for arg in extra if arg != "--yes"]
        if extra:
            raise LadderError(f'task "{name}" accepts extra args only with 1 run line')
    print(f"ladder: using {plain(config.path)}", file=err, flush=True)
    with logged(runner, out, name) as (tee, path):
        total = len(task.run)
        for step, line in enumerate(task.run, 1):
            label = f"ladder: FAIL {plain(name)}, step {step} of {total}"
            try:
                code = runner.stream(command(task, line, extra), cwd=str(Path(config.path).parent))
            except StepTimeout as error:
                summary(tee, f"{label}, timeout after {error.seconds:g}s (exit {TIMEOUT_EXIT}); full log: {path}")
                return TIMEOUT_EXIT
            except LadderError:
                summary(tee, f"{label}, exit 1; full log: {path}")
                raise
            if code:
                summary(tee, f"{label}, exit {code}; full log: {path}")
                return code
        summary(tee, f"ladder: ok {plain(name)}, {total} {'step' if total == 1 else 'steps'}; full log: {path}")
    return 0
