# Decisions

Agreed with Ahmed in a grilling session on 2026-11-01. Each line is a decision, then the reason in plain words. Newer decisions go at the bottom; an old one is changed by adding a new line that says which one it replaces.

## The tool

1. **Name: `ladder`.** Agents should not climb the same ladder again each time. 1 short word to type: `ladder pr comments 53`.
2. **Repo: `Ahmed-Ahmed16/ladder-cli`, public, on disk at `D:\Ahmed-yzh\ladder-cli`.** It holds no company data, and public means any laptop installs it with no sign in.
3. **Nothing from a company project goes in this repo.** No names, paths, code or tokens. Tests use made up repos, PRs and comments only.
4. **Language: Python 3.12, standard library only.** Most projects and the existing DevOps tools are Python. No extra packages means nothing breaks on a package update. Python reads TOML by itself since 3.11.
5. **Tests: Python's built in `unittest`.** Pure parsing and deciding sit in functions with unit tests. A thin layer calls `gh`, `git` and friends.
6. **Install: `pip install git+https://github.com/Ahmed-Ahmed16/ladder-cli`.**

## 1 front door

7. **Core jobs and project tasks are 1 menu.** `ladder list` shows both. An agent never needs a second tool to find a job.
8. **No `just`.** It would be a second front door and a second install. Ladder runs its own small tasks.

## The project file

9. **`ladder.toml` at the repo root, committed, company repos included.** Visible, not hidden, so people and agents notice it.
10. **A task is a name plus:** `about` (required, 1 plain line), `run` (1 command, or a list run in order that stops at the first failure), optional `shell = "bash"` when a pipe or `&&` is needed, and optional `confirm = true`.
11. **No shell by default.** Ladder splits the command into words and starts the program itself, so it behaves the same in PowerShell and Git Bash. A task that needs a shell names it.
12. **`confirm = true` means ladder refuses to run the task without `--yes`.** For tasks that touch a live server, such as a deploy.
13. **Extra arguments pass through.** `ladder deploy abc123 --yes` hands `abc123` to the task's command.
14. **A task with the same name as a core job makes ladder refuse the file** and name the clash. No silent winner, so a core job means the same thing in every repo.
15. **`[gates]` has the task shape plus an optional `ci` file path.** `ladder gates` runs the steps, stops at the first failure, and prints pass or fail per step. `--dry-run` only prints them. With `ci` set, a gate step that does not appear in that file gives a warning, never a failure.
16. **`[review] wait_for` is a list of GitHub logins.** It can be a bot (Greptile) or a person (`/debate-review` posts as Ahmed). `ladder pr wait-review` waits until each one has reviewed the newest commit. `--bot` overrides the list. An empty or missing list stops at once with a clear message, never an endless wait.

## Agent wiring

17. **`ladder install-skill` writes the same skill page to 2 places and 1 section:** `~/.claude/skills/ladder/SKILL.md` (Claude Code), `~/.agents/skills/ladder/SKILL.md` (Codex), and a section in `~/.codex/AGENTS.md` between marker lines, so a rerun replaces it and never doubles it. The page lives in this repo, so an update is a reinstall plus 1 command.

## Rules every command keeps (from werdy)

18. Print each outside command before running it. Return a plain error, never a crash trace. Never print a secret. Write nothing into a repo unless that is the command's job.

## Facts checked, not decisions

* The work laptop is this PC (`AHMED-YZH`): Windows 11 Pro, Python 3.12.10, `gh` 2.98.0, Codex 0.164.0. Checked 2026-11-01.
* Codex skill folders on this PC: `~/.codex/skills` and `~/.agents/skills` both exist and hold skills. Not tested: that Codex loads `~/.agents/skills` without being told.
* The main company project has no review bot on its PRs today (8 PRs checked).

## Still unknown

* Installing from the personal GitHub on the work laptop is assumed allowed: `___`.
* Greptile's GitHub login: `___` (Ahmed adds it later).
