---
name: ladder
description: Use ladder when about to write a script for a repeated job, run checks before a commit, read PR review comments, wait for a reviewer, or run a project's tests, build or deploy steps.
---

# Use ladder first

Before writing any script, run `ladder list` in the repo.
If a task exists, use it.
If a task is broken or outdated, fix its script in place.
Never write a second script for the same job.
A script used once may stay in a temp folder.
For a script the job will need again:

1. Save it in `scripts/ladder/` in the repo.
2. Run `ladder add <name> --about "..." --run "..."`.
3. Run it once with `ladder <name>` to prove it works.
4. Put the script and the ladder.toml change in the same commit as the work.

In company repos, the task reaches Ahmed through the same PR.
Never hand edit ladder.toml to add a task; use `ladder add`.
Never put a path outside the repo in its ladder.toml.
Personal scripts get tasks in their own folder's ladder.toml.
Read `ladder help` and `ladder <job> --help` for arguments.

| Job | Use |
| --- | --- |
| `help` | Show commands and help. |
| `list` | Show core jobs and project tasks. |
| `doctor` | Check tools, sign in, Python and config. |
| `pr comments <n> [--all] [--full]` | Read unresolved review threads; include resolved threads or whole bodies. |
| `pr wait-review <n> [--bot login] [--timeout-mins N]` | Wait for each login in `[review] wait_for` to review the newest commit; repeat `--bot` to replace the list. |
| `gates [--dry-run]` | Run checks; dry run only prints the steps. |
| `add <name> --about TEXT --run LINE` | Add a task to ladder.toml. Repeat `--run` for more steps; use `--shell bash` or `--confirm` when needed. |
| `init` | Create a starter ladder.toml at the git repo root. |
| `install-skill` | Install this page for Claude and Codex. |
| `<task> [args]` | Run a project task. Extra args need 1 command. |

Put `ladder` before each job: `ladder gates`.
Ladder reads only the nearest git repo root's ladder.toml.
It reads no config outside a git repo. Subfolder configs are ignored.
In human mode, tasks and gates print `ladder: using <path>` to standard error before steps.

`$ ...` lines show the outside commands ladder ran.
Gates print PASS for each passing step and FAIL for a failed step.
Doctor prints ok or FAIL for each check, then the overall result.
Wait-review prints `<sha>: waiting for <logins>` only when status changes, then `<sha>: done: <login> (<STATE>), ...` when all finish.
It reports head changes, polls every 30 s, and exits 1 on timeout (default 20 min) or when no reviewer is set.
Exit 0 means success. A failed task or gate returns the step's exit code.
Input errors and doctor failures exit 1. Failure stops later steps.

Every task and gates run writes its whole output to a log file in the temp folder.
It ends with 1 summary line that names that file. The last line is the result.
Do not pipe ladder into `tail`, `head` or `grep` to find it. Run `ladder gates` alone, then read the last line.
Example of a failed task, then a passing one:

```text
ladder: FAIL test, step 1 of 1, exit 3; full log: /tmp/ladder/logs/test-20261115-101500.log
ladder: ok test, 2 steps; full log: /tmp/ladder/logs/test-20261115-101530.log
```

Gates end with `FAIL step 2 of 3: <command> (exit 2); full log: <path>` or `gates: all 3 passed; full log: <path>`.
Read the log file for the rest of the output.
Set `LADDER_TIMEOUT=<seconds>` to stop a step that runs too long.
The line then says `timeout after <N>s (exit 124)`.
`needs --yes` means ask the human first. Never add `--yes` on your own.

## Reading a log

Run `ladder log gates --grep FAIL` to read the newest gates log.
Pass a task name, a file name, or the full log path from the summary.
Ladder reads regular `.log` files only from its private log folder and rejects file links.
It selects regex matches first, then the first `--head N` or last `--tail N` lines.
The default is the last 40 lines or matches. Do not combine `--head` and `--tail`.
Each line has at most 300 characters. `--max-chars N` caps log text at 4000 by default.
The header and cut marker are extra. No regex matches exits 1; a match exits 0.
Numbers must be whole numbers >= 1. Secrets stay redacted.

## Agent mode

Agent mode is on when `CLAUDECODE` is non-empty and stdout is not a terminal.
Set `LADDER_AGENT=0` or put `--human` first for full human output.
Set `LADDER_AGENT=1` to force agent mode.
Agent mode drops the `ladder: using <path>` line, including dry runs.
`ladder doctor` shows the mode and the config path.
Example: `ladder doctor` prints `ok   mode: agent (CLAUDECODE set, no TTY)`.

### Output cap

In agent mode, tasks and gates show the first 10 and last 30 output lines.
If output exceeds 40 lines, a `showing 40 of M lines (N cut); full log: <path>` line separates them.
The full log keeps all output. With 40 lines or fewer, all lines show without a cut line.
The summary stays last. Use `ladder --human` or `LADDER_AGENT=0` to show all lines.

Minimal ladder.toml:

```toml
[tasks.test]
about = "Run the tests"
run = "python -m unittest discover -s tests -t ."

[gates]
run = ["python -m unittest discover -s tests -t ."]
```

Run `ladder test` for the task, or `ladder gates` for the checks.
Steps run from the repo root. No shell is used by default.
Use `shell = "bash"` on a task only when it needs shell features.
Bash tasks run with pipefail, so a failed command before a pipe fails the task.
Use `confirm = true` for a task that needs human approval.
