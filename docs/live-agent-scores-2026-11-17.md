# Live agent scores, 2026-11-17

Harness: `tests/live/run_live.py` (`python -m tests.live.run_live b3|b3noskill|b4|b5`). Counts and labels only. Transcripts stay outside git in `D:\Ahmed-yzh\ladder-live-runs-2026-11-17`.
Build under test: `ladder` on PATH, reinstalled from 2f2ad6d. Prompts, answer keys and scoring come from `tests/frozen` (`agent_questions.py`, `contracts.json`), unchanged.

## Method

- One fresh `claude -p` session per question per run. Model `claude-sonnet-5-5`. `--no-session-persistence`, `--max-budget-usd 0.75`, no MCP servers.
- `--setting-sources project`: no user CLAUDE.md, no user skills, no hooks. Checked once: the agent said it had no CLAUDE.md or memory text.
- The installed skill (byte copy of `~/.claude/skills/ladder/SKILL.md`, dated 2026-11-16) sits in each lab as a project skill. The agent can load it with the Skill tool.
- Tools: B3 and B4 `Bash, Read, Skill`. B5 `Read, Skill` only (no shell).
- B4: `gh` is `tests/frozen/fake_gh.py` behind a PATH shim. 6 states x 3 runs = 18 sessions. No network.
- "Tool calls" counts every tool call, the Skill load included. "Shell calls" counts Bash only.
- Pipes are counted with `count_piped_calls` from the frozen contract.

## Result

| Row | Pass rule | Answers right | Verdict |
| --- | --- | --- | --- |
| B3a/B3b, skill available | 3 of 3 runs, at most 2 calls, no pipe | 3 of 3 runs right | FAIL on the strict rule (3 tool calls); PASS if the Skill load is not counted (2 shell calls, 0 pipes) |
| B3a/B3b, no skill (extra arm) | same | 3 of 3 runs right | FAIL: 1 of 3 runs within 2 calls |
| B4 | all right, 1 ladder call per state, 0 false green | 18 of 18 sessions right, 0 false green | FAIL: `pr-api-error` used 2 ladder calls in 3 of 3 runs |
| B5 | 2 of 2 tasks in 3 of 3 runs | 6 of 6 right | PASS |

## B3a/B3b detail (`longfail`, error at line 150)

| Arm | Run | Right | Tool calls | Shell calls | Pipes |
| --- | --- | --- | --- | --- | --- |
| skill | 1 | yes | 3 | 2 | 0 |
| skill | 2 | yes | 3 | 2 | 0 |
| skill | 3 | yes | 3 | 2 | 0 |
| no skill | 1 | yes | 2 | 2 | 0 |
| no skill | 2 | yes | 5 | 5 | 2 |
| no skill | 3 | yes | 5 | 5 | 2 |

With the skill, each run loaded the skill (1 call), ran the task, then ran `ladder log <task> --grep ...`. No pipe in any run. Without the skill, 2 of 3 runs used pipes and 5 calls.

## B4 detail

Each run covers 6 states. Per state, 3 runs:

| State | Right | Ladder calls (runs 1, 2, 3) | False green |
| --- | --- | --- | --- |
| pr-green | 3 of 3 | 1, 1, 1 | 0 |
| pr-one-failed | 3 of 3 | 1, 1, 1 | 0 |
| pr-review-pending | 3 of 3 | 1, 1, 1 | 0 |
| pr-no-checks | 3 of 3 | 1, 1, 1 | 0 |
| pr-log-missing | 3 of 3 | 1, 1, 1 | 0 |
| pr-api-error | 3 of 3 | 2, 2, 2 | 0 |

On `pr-api-error`, `ladder pr status` exited 1 with one error line. The agent ran the same command a second time, then answered `unknown`. Whether a retry after an outage is wrong is a call for Ahmed; the frozen rule says 1 call.
Every session used the Skill tool first, then 1 Bash call (except `pr-api-error`). 0 pipes in all 18.

## B5 detail

| Task | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- |
| check_before_commit (`ladder gates`) | right | right | right |
| pr_green (`ladder pr status`) | right | right | right |

In 2 runs of `pr_green` the agent tried a Bash call. Bash was not offered, so the call was refused. The answer was right anyway.

## Cost and tokens

| Part | Sessions | Cost (USD) | Tokens (input + cache + output) |
| --- | --- | --- | --- |
| B3 skill arm | 3 | 0.1184 | 144,320 |
| B3 no-skill arm | 3 | 0.0990 | 154,112 |
| B4 | 18 | 0.6078 | 656,658 |
| B5 | 6 | 0.1915 | 130,622 |
| Setup trials (2, not scored) | 2 | 0.0453 | ___ |
| Total | 32 | 1.0620 | 1,085,712 + trials ___ |

Cost is `total_cost_usd` from each session's result event. The budget stop was $5. It was not reached.

## Limits

- n = 3 per cell. The three runs of each cell gave near identical token counts, so this shows the agent's usual path, not the spread over many tries.
- The skill is loaded by the agent itself (Skill tool). The skill load adds 1 call to every run. Whether that load counts against "at most 2 calls" is the open call for B3.
- The fake `gh` and the lab are lab fixtures, as in B6b. Real PR logs are not tested.
- The agent ran with Ahmed's normal environment variables and an unrestricted Bash tool inside a lab folder. No Bash allowlist was used, because an allowlist would stop pipes and hide the pipe count.
- B5 had no shell. It tests which command the skill text leads to, not that the command runs.
- Billing path: `claude -p` with the signed in login, not the API worker. The cost figures are the CLI's own.
