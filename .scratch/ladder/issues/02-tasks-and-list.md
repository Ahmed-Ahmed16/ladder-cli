# 02: ladder.toml tasks and ladder list

**What to build:** A repo's `ladder.toml` defines tasks. `ladder list` shows core jobs and tasks together, 1 line each. `ladder <task> [args]` runs it (decisions D9 to D14). `doctor` reports whether the file was found and parsed. Ahmed types the config reader himself, with guidance.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Task needs `about` and `run`; `run` is 1 command or a list run in order, stopping at the first failure
- [ ] No shell by default; `shell = "bash"` runs the line through bash
- [ ] `confirm = true` refuses without `--yes`
- [ ] Extra arguments pass through to the command
- [ ] A task named like a core job: the file is refused and the clash named
- [ ] Missing `about`, wrong types and bad TOML each give 1 plain error naming file and task
