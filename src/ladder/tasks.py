from pathlib import Path
import shlex

from .process import LadderError


def command(task, line, extra):
    if task.shell == "bash":
        return ["bash", "-c", line + (" " + shlex.join(extra) if extra else "")]
    try:
        argv = shlex.split(line, posix=True)
    except ValueError as error:
        raise LadderError(f'task "{task.name}": {error}') from error
    if not argv or not argv[0]:
        raise LadderError(f'task "{task.name}": run must name a program')
    return [*argv, *extra]


def run_task(config, argv, runner, err):
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
    for step, line in enumerate(task.run, 1):
        code = runner.stream(command(task, line, extra), cwd=str(Path(config.path).parent))
        if code:
            print(f"ladder: step {step} of {len(task.run)} failed (exit {code})", file=err)
            return code
    return 0
