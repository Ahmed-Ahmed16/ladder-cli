from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import tomllib

from .process import LadderError


@dataclass(frozen=True)
class Task:
    name: str
    about: str
    run: tuple[str, ...]
    shell: str | None = None
    confirm: bool = False


@dataclass(frozen=True)
class Config:
    path: str
    tasks: dict[str, Task]
    gates: dict
    review: dict


CORE_JOBS = ("help", "list", "doctor", "pr", "gates", "init", "install-skill")


def repo_root(start) -> Path | None:
    folder = Path(start).resolve()
    for candidate in (folder, *folder.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def find(start: str) -> str | None:
    root = repo_root(start)
    if root is None:
        return None
    path = root / "ladder.toml"
    return str(path) if path.is_file() else None


def load(start) -> Config | None:
    path = find(start)
    if path is None:
        return None
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise LadderError(f"{path}: could not read: {error}") from error
    return parse(text, path)


def parse(text: str, path: str) -> Config:
    '''
    1. Bad TOML -> LadderError "<path>: not valid TOML: <reason>".
    2. Allowed top level keys: tasks, gates, review. Any other -> LadderError "<path>: unknown section \"<key>\"".
    3. tasks is a table of tables. Each task: `about` required non empty string; `run` required, a non empty string or a non empty list of non empty strings (a string becomes a 1 item tuple); `shell` optional, only "bash"; `confirm` optional bool. Any other key -> error naming it. Each error: LadderError "<path>: task \"<name>\": <problem>".
    4. A task name in CORE_JOBS -> LadderError "<path>: task \"<name>\" clashes with the core job \"<name>\", rename it".
    5. gates accepts optional string about, required run (same rules as tasks),
       and optional non empty relative ci path. Unknown keys are errors.
       Missing gates is an empty dict; present gates has run as a tuple.
       Review is kept without validation.
    '''
    try:
        sections = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise LadderError(f"{path}: not valid TOML: {error}") from error
    for key in sections:
        if key not in ("tasks", "gates", "review"):
            raise LadderError(f'{path}: unknown section "{key}"')
    task_tables = sections.get("tasks", {})
    if not isinstance(task_tables, dict):
        raise LadderError(f'{path}: task "tasks": must be a table of tables')
    tasks = {}
    for name, settings in task_tables.items():
        tasks[name] = parse_task(settings, name, path)
    gates = parse_gates(sections["gates"], path) if "gates" in sections else {}
    return Config(path, tasks, gates, sections.get("review", {}))


def non_empty_text(text):
    return isinstance(text, str) and bool(text.strip())


def parse_run(run, prefix):
    if isinstance(run, str):
        run = [run]
    if not isinstance(run, list) or not run or not all(non_empty_text(line) for line in run):
        raise LadderError(prefix + "run must be a non empty string or list of non empty strings")
    return tuple(run)


def parse_gates(settings, path):
    prefix = f"{path}: gates: "
    if not isinstance(settings, dict):
        raise LadderError(prefix + "must be a table")
    for key in settings:
        if key not in ("about", "run", "ci"):
            raise LadderError(prefix + f'unknown key "{key}"')
    if "about" in settings and not isinstance(settings["about"], str):
        raise LadderError(prefix + "about must be a string")
    run = parse_run(settings.get("run"), prefix)
    if "ci" in settings:
        ci = settings["ci"]
        if not non_empty_text(ci) or PureWindowsPath(ci).anchor:
            raise LadderError(prefix + "ci must be a non empty relative path")
    return {**settings, "run": run}


def parse_task(settings, name, path):
    if name in CORE_JOBS:
        raise LadderError(f'{path}: task "{name}" clashes with the core job "{name}", rename it')
    prefix = f'{path}: task "{name}": '
    if not isinstance(settings, dict):
        raise LadderError(prefix + "must be a table")
    for key in settings:
        if key not in ("about", "run", "shell", "confirm"):
            raise LadderError(prefix + f'unknown key "{key}"')
    about = settings.get("about")
    if not non_empty_text(about):
        raise LadderError(prefix + "about must be a non empty string")
    run = parse_run(settings.get("run"), prefix)
    shell = settings.get("shell")
    if "shell" in settings and shell != "bash":
        raise LadderError(prefix + 'shell must be "bash"')
    confirm = settings.get("confirm", False)
    if not isinstance(confirm, bool):
        raise LadderError(prefix + "confirm must be a bool")
    return Task(name, about, run, shell, confirm)
