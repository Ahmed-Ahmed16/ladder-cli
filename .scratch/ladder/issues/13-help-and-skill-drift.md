# 13: help and skill text cannot drift

**What to build:** Fix the stale help text and the misleading gates error, and add a test that fails when a job or flag is missing from the skill page. Checklist item 7 in `docs/talk-checklist-2026-11-15.md`.

**Why:** The talk: skill and help text are the interface, and stale text is a bug, because agents follow it. Found 2026-11-15:

* The help description `help | list | doctor | pr comments | pr wait-review | add | <task> [args]` leaves out `gates`, `init` and `install-skill` (`src/ladder/cli.py:61`).
* `ladder gates` in a repo with no `ladder.toml` says `no [gates] in ladder.toml` (`src/ladder/cli.py:170`). Seen in this repo, which has no `ladder.toml`.

**Blocked by:** none

**Status:** ready-for-agent

- [ ] Build the help description from `config.CORE_JOBS`, so a new job shows up by itself.
- [ ] `ladder gates` with no `ladder.toml` says `no ladder.toml at the repo root; run ladder init`. With a file but no `[gates]`, the old message stays.
- [ ] Test: every name in `config.CORE_JOBS` appears in `ladder help` output and in the job table of the packaged `SKILL.md`.
- [ ] Test: every long flag the parser knows (walk the subparsers' actions) appears in the packaged `SKILL.md`.
- [ ] Optional: add a `ladder.toml` to this repo with `[tasks.test]` and `[gates]`, so ladder runs its own tests.

**Test idea:** The drift check is a helper that takes the skill text and returns the missing names. Positive: the real `SKILL.md` gives an empty list. Known negative: the same text with the `gates` row removed gives `["gates"]`, and with `--timeout-mins` removed gives that flag. Gates test with no config checks the new message; with a config but no `[gates]` it checks the old one.

**Size:** about 25 code lines and 70 test lines.
