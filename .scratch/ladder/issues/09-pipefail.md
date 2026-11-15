# 09: pipefail for bash tasks

**What to build:** A task with `shell = "bash"` runs `bash -o pipefail -c <line>`, so a failed command before a pipe fails the task. Checklist item 2 in `docs/talk-checklist-2026-11-15.md`.

**Why:** Today the task runs `bash -c <line>` (`src/ladder/tasks.py:9`). Lab, 2026-11-15: `run = "python gen.py 2 5 | cat"` exited 5 inside, and ladder reported exit 0. That is a false pass, the worst failure the talk names.

**Blocked by:** none

**Status:** ready-for-agent

- [ ] `command()` in `src/ladder/tasks.py` returns `["bash", "-o", "pipefail", "-c", line ...]`.
- [ ] The printed command shows `-o pipefail`, so the screen matches what ran (D18).
- [ ] Do not add `-e`. It changes how `&&` and `if` lines behave.
- [ ] Skill page and README say bash tasks run with pipefail.
- [ ] Note in the README: a task that pipes into `head` can now fail with exit 141 when the reader closes early. In 1 company repo's `ladder.toml`, 4 bash tasks exist and none pipes at the top level today.

**Test idea:** Unit test that `command()` for a bash task holds `-o pipefail`. Real runner checks with Git Bash: `exit 5 | cat` returns 5; known negative: `true | cat` returns 0. The existing extra arguments test still passes.

**Size:** about 5 code lines and 40 test lines.
