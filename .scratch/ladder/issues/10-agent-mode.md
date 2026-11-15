# 10: agent mode switch

**What to build:** Ladder knows when an agent calls it. 1 function decides the mode from the environment; `doctor` shows the mode. This ticket changes no other output; ticket 11 uses the mode. Checklist item 6 in `docs/talk-checklist-2026-11-15.md`.

**Why:** No source line reads `CLAUDECODE` today. The talk's advice: an agent mode lets a CLI print less for agents and keep the full view for a person at a terminal.

**Blocked by:** none

**Status:** ready-for-agent

- [ ] `agent_mode(environ) -> tuple[bool, str]` returns the mode and the reason.
- [ ] `LADDER_AGENT=1` gives agent, `LADDER_AGENT=0` gives human. This override wins over everything else.
- [ ] Else `CLAUDECODE=1` gives agent. Verified set to `1` in a Claude Code session on 2026-11-15.
- [ ] Else Codex's variable gives agent: `___`. Check with `codex exec "print the environment variable names"` before building, and add it only if 1 is found.
- [ ] Else human.
- [ ] `Context` gets the mode, so tests pass it in and never touch the real environment.
- [ ] `doctor` prints `ok   mode: agent (CLAUDECODE=1)` or `ok   mode: human`. This line never fails.
- [ ] Skill page names `LADDER_AGENT=0` as the way to get human output.

**Test idea:** Table test over environment dicts: `{}` gives human; `{"CLAUDECODE": "1"}` gives agent; `{"CLAUDECODE": "1", "LADDER_AGENT": "0"}` gives human; `{"LADDER_AGENT": "1"}` gives agent. Known negative: `{"CLAUDECODE": ""}` gives human. Doctor test checks the mode line text.

**Size:** about 30 code lines and 60 test lines.
