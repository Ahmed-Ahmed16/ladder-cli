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
Tasks and gates print `ladder: using <path>` to standard error before steps.

`$ ...` lines show the outside commands ladder ran.
Gates print PASS for each passing step and FAIL for a failed step.
Doctor prints ok or FAIL for each check, then the overall result.
Wait-review prints `<sha>: waiting for <logins>` only when status changes, then `<sha>: done: <login> (<STATE>), ...` when all finish.
It reports head changes, polls every 30 s, and exits 1 on timeout (default 20 min) or when no reviewer is set.
Exit 0 means success. A failed task or gate returns the step's exit code.
Input errors and doctor failures exit 1. Failure stops later steps.
`needs --yes` means ask the human first. Never add `--yes` on your own.

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
Use `confirm = true` for a task that needs human approval.
