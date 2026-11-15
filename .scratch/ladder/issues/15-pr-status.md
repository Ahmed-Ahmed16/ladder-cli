# 15: ladder pr status, one compact PR summary

**What to build:** `ladder pr status` prints the PR of the current branch in a few lines: merge state, the check counts with the names of failed checks, the count of unresolved review threads, and the PR URL. It prints no log text. Long lists follow the cap rules of ticket 11.

**Why:** The transcript audit (2026-11-15) counts Claude calls of `gh` at 3825 in all time. At least 1938 of them were piped into `head`, `grep`, `tail`, `sed` or a similar tool (about 51%). The pipes count is the sum of the `gh` pipe pairs in `research/transcript-audit-2026-11-15.json`, so it is a floor. Ladder has `pr comments` and `pr wait-review` but no short status read.

**Blocked by:** none (reuses the GraphQL access in `src/ladder/pr.py`; ticket 12 may share its code)

**Status:** ready-for-agent

- [ ] `ladder pr status` takes no arguments and reads the PR of the current branch through `gh`.
- [ ] Output is at most 12 lines: a state line, a checks line such as `checks: 5 pass, 1 fail: <name>`, a threads line such as `threads: 2 unresolved`, and the PR URL.
- [ ] Failed check names print. Log text does not print. The skill page says to use `gh run view --log` for logs.
- [ ] No PR on the branch: exit 1 with 1 line of text. `gh` missing: exit 1 with 1 line of text.
- [ ] The job appears in the job table of the packaged `SKILL.md` (ticket 13 drift test checks it).
- [ ] Skill page: "Run `ladder pr status` before `gh pr view`."

**Test idea:** Saved `gh` JSON fixture with 5 checks, 1 failed and 2 unresolved threads. Expect the 3 content lines and the URL. Known negative: a fixture with no PR gives exit 1 and 1 line. Check that the output never holds the log text of a failed check.

**Size:** about 70 code lines and 80 test lines.
