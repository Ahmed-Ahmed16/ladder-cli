| Row | Case | Status | False success | Reason |
| --- | --- | --- | --- | --- |
| B2 | tty=yes,claudecode=set,override=none | FAIL | 0 |  |
| B2 | tty=yes,claudecode=set,override=LADDER_AGENT=1 | FAIL | 0 |  |
| B2 | tty=yes,claudecode=set,override=LADDER_AGENT=0 | FAIL | 0 |  |
| B2 | tty=yes,claudecode=unset,override=none | FAIL | 0 |  |
| B2 | tty=yes,claudecode=unset,override=LADDER_AGENT=1 | FAIL | 0 |  |
| B2 | tty=yes,claudecode=unset,override=LADDER_AGENT=0 | FAIL | 0 |  |
| B2 | tty=no,claudecode=set,override=none | FAIL | 0 |  |
| B2 | tty=no,claudecode=set,override=LADDER_AGENT=1 | FAIL | 0 |  |
| B2 | tty=no,claudecode=set,override=LADDER_AGENT=0 | FAIL | 0 |  |
| B2 | tty=no,claudecode=unset,override=none | FAIL | 0 |  |
| B2 | tty=no,claudecode=unset,override=LADDER_AGENT=1 | FAIL | 0 |  |
| B2 | tty=no,claudecode=unset,override=LADDER_AGENT=0 | FAIL | 0 |  |
| B5 | B5 | NOT_RUN | 0 | not_built_before_b5 |
| agent_questions | lab_gates | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | lab_gates_agent_mode | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | lab_longfail150 | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | pr_states | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | tasks_b5 | NOT_RUN | 0 | no_live_agent_run_in_b0 |

| Row | Pass | Fail | Not run | False success |
| --- | --- | --- | --- | --- |
| B2 | 0 | 12 | 1 | 0 |
| B5 | 0 | 0 | 1 | 0 |
| overall | 0 | 12 | 6 | 0 |
