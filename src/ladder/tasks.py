from pathlib import Path
import shlex

from .process import LadderError, plain, split_command


def command(task, line, extra):
    if task.shell == "bash":
        return ["bash", "-c", line + (" " + shlex.join(extra) if extra else "")]
    return [*split_command(line, f'task "{task.name}"'), *extra]


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
    print(f"ladder: using {plain(config.path)}", file=err, flush=True)
    for step, line in enumerate(task.run, 1):
        code = runner.stream(command(task, line, extra), cwd=str(Path(config.path).parent))
        if code:
            print(f"ladder: step {step} of {len(task.run)} failed (exit {code})", file=err)
            return code
    return 0
