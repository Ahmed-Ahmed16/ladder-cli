# Spec: ladder, 1 front door for every project's jobs

Written 2026-11-01 from the grilling session. Decisions are numbered in `docs/decisions.md`; this spec refers to them as D1, D2 and so on. Words follow `GLOSSARY.md`.

## Problem Statement

Agents (Claude Code, Codex) and Ahmed keep writing throwaway scripts for jobs that come back every week: run the checks before a commit, read the review comments on a PR, wait for a reviewer, run a project's tests or deploy listing. Each session learns the steps again, and each copy is a little different and a little wrong. werdy fixed this inside 1 repo with a tested `cargo xtask` plus a skill. Every other project, on this laptop, still has the problem.

## Solution

A small Python program, `ladder`, installed once per laptop. It gives 1 front door: `ladder list` shows the core jobs (the same in every repo) and the project's own tasks (read from `ladder.toml` at the repo root). Agents are told once, by a skill and an `AGENTS.md` section, "use ladder, never a throwaway script". A job written once is reused by every agent and by Ahmed.

## User Stories

1. As an agent, I want `ladder list` to show every job in this repo with 1 line each, so that I find an existing job before I write a script.
2. As an agent, I want `ladder help` and `ladder <job> --help`, so that I learn a job's arguments without reading source.
3. As Ahmed, I want to install ladder with 1 `pip install git+...` command, so that a new laptop is ready in a minute.
4. As Ahmed, I want ladder to need nothing beyond Python 3.12's standard library, so that a package update never breaks it.
5. As an agent, I want `ladder doctor` to say whether `git` and `gh` are installed and `gh` is signed in, so that I know at once why a job will fail.
6. As an agent, I want `ladder doctor` to say whether `ladder.toml` was found and parsed, so that a broken file is caught before a job runs.
7. As an agent, I want `ladder doctor` to end with 1 overall pass or fail line and a matching exit code, so that I read 1 line, not a screen.
8. As an agent, I want `ladder pr comments <n>` to show unresolved review threads with file and line, so that I see what to fix.
9. As an agent, I want each comment cut to its first 3 plain lines by default, so that bot noise (HTML, `<details>` logs) does not flood my context.
10. As an agent, I want `--full` to show whole comment bodies, so that I read a long comment when I need it.
11. As an agent, I want `--all` to include resolved threads after the unresolved ones, so that I see the full history when I need it.
12. As an agent, I want a first line like `PR #82: 1 unresolved of 2 threads`, so that I know the count at once.
13. As an agent, I want a wrong PR number to give a plain error that names the PR number, so that I fix my input and do not guess.
14. As an agent, I want every outside command printed before it runs, so that I and Ahmed see exactly what ladder did.
15. As Ahmed, I want ladder never to print a token or secret, so that a log or chat never leaks one.
16. As an agent, I want any failure to be 1 plain error line and a non zero exit code, never a Python trace, so that I know what went wrong.
17. As a project, I want tasks in `ladder.toml` with `about` and `run`, so that my existing scripts sit in the same menu as core jobs.
18. As a project, I want `run` to accept a list of commands that stops at the first failure, so that a multi step task needs no `&&`.
19. As a project, I want `shell = "bash"` on a task, so that a pipe works where it is needed, and only there.
20. As Ahmed, I want `confirm = true` to make a task refuse to run without `--yes`, so that an agent never deploys by accident.
21. As an agent, I want extra arguments after the task name passed to its command, so that `ladder deploy abc123 --yes` works.
22. As Ahmed, I want ladder to refuse a `ladder.toml` whose task shares a core job's name, so that a core job means the same in every repo.
23. As Ahmed, I want a task with no `about` to be an error, so that the menu always says what each job does.
24. As an agent, I want `ladder gates` to run the project's pre commit checks and print pass or fail per step, so that I run what CI runs before a commit.
25. As an agent, I want `ladder gates --dry-run` to print the steps only, so that I check them without running them.
26. As Ahmed, I want a warning when a gate step is missing from the named CI file, so that local gates do not drift from CI.
27. As an agent, I want `ladder pr wait-review <n>` to wait until each login in `[review] wait_for` has reviewed the newest commit, so that I do not poll by hand.
28. As an agent, I want `--bot <login>` to override that list, so that I wait for 1 reviewer on demand.
29. As an agent, I want wait-review to stop at once with a clear message when no reviewer is set, so that I never wait forever.
30. As an agent, I want wait-review to stop with a clear error after a timeout, so that a missing reviewer does not hang my session.
31. As Ahmed, I want `ladder install-skill` to write the skill to the Claude and Codex skill folders and a marked section in `~/.codex/AGENTS.md`, so that both agents learn the rule from 1 command.
32. As Ahmed, I want a rerun of `install-skill` to replace its section, never duplicate it, so that updates are safe.
33. As Ahmed, I want `ladder init` to write a starter `ladder.toml` and print the 2 lines for the repo's `AGENTS.md`, so that a new project is set up in 1 command.
34. As Ahmed, I want ladder to run the same in PowerShell and Git Bash on Windows, so that Claude and Codex get the same result.

## Implementation Decisions

- 1 Python package, `ladder`, with a console entry point named `ladder` (D1, D4, D6). Python 3.12, standard library only.
- **Runner seam.** Every outside program goes through 1 runner object with 2 operations: run and stream output (for tasks and gates), and run and capture output (for `gh` and `git` queries). The runner prints the command before running it. The CLI entry takes the argument list, a runner and an output stream, and returns an exit code. Real use builds the real runner; tests pass a fake.
- **Argument parsing** with the standard library parser. Core jobs: `help`, `list`, `doctor`, `pr comments`, `pr wait-review`, `gates`, `init`, `install-skill`. Any other first word is looked up as a task.
- **Errors.** A single error type carries a plain message. The entry point catches it, prints 1 line to standard error, and exits with code 1. Unexpected exceptions are also turned into 1 line, with no trace, unless a debug environment variable is set.
- **`pr comments`** is a port of werdy's `pr.rs`: the same GraphQL query through `gh api graphql` with `{owner}` and `{repo}` filled by `gh`, the same parse, render and summary rules (unresolved first, sorted by path and line, `[resolved]` and `[outdated]` marks, 3 line summary that drops HTML tags, HTML comments and whole `<details>` blocks, `**` removed).
- **`doctor`** checks: `git --version`, `gh --version`, `gh auth status` (exit code only, its output is never printed, since it can show a token hint), Python version, and whether `ladder.toml` exists and parses. Each check prints 1 line. Exit code 0 only when all pass.
- **Config module** (later ticket): reads `ladder.toml` with `tomllib`, validates tasks (D10 to D15) and returns plain data. Errors name the file, the task and the problem. Good piece for Ahmed to type himself.
- **Tasks** run with no shell by default: the command line is split into words with `shlex` in POSIX mode and started directly (D11). `shell = "bash"` runs the line through `bash -c`.
- **`wait-review`** (later ticket) reads PR reviews through `gh`, keyed by login and commit id, instead of werdy's CodeRabbit check run, because a reviewer here can be a person (D16). Poll every 30 s, default timeout `___` minutes (werdy's default: `___`, check before building).
- **`install-skill`** (later ticket): the skill page ships inside the package. The `AGENTS.md` section sits between `<!-- ladder:start -->` and `<!-- ladder:end -->` markers.

## Testing Decisions

- A good test calls the CLI entry with real arguments and a fake runner, then checks only the printed text and the exit code. It never imports inner functions just to test them, unless a pure function (such as the comment summary) has many edge cases worth naming one by one.
- The fake runner returns saved answers keyed by command, and records the commands it got, so a test can assert what ladder ran and what it printed first.
- No test touches the real GitHub, the network, or the real home folder. Tests that write files use a temporary folder.
- Prior art: werdy's 7 tests in `pr.rs` port over with the same saved JSON (paths and logins in it are made up: `src/a.rs`, `coderabbitai`, `Ahmed-Ahmed16`, `https://x/1`).
- Every check gets a known positive and a known negative case, so a check that can never fail is caught.
- Run with `python -m unittest discover` from the repo root.

## Out of Scope

- A second git host (GitLab, Azure DevOps). Only GitHub through `gh`.
- `just`, `mise` or `task` support.
- Domain jobs such as werdy's `apk inspect`. They stay in their project, reachable as a task.
- Moving werdy onto ladder. That is a werdy issue after ladder's first release.
- Publishing to PyPI or building a single file binary.

## Further Notes

- Ticket 1 (tracer bullet): repo skeleton, install from git on Windows, `help`, `doctor`, `pr comments` with ported tests, then install on PATH and confirm from outside the sandbox.
- Ahmed is learning; each ticket explains its steps, and the config parser is flagged for him to type.
- Unknowns: install from personal GitHub on the work laptop assumed allowed `___`; Greptile login `___`.
