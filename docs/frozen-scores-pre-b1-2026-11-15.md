| Row | Case | Status | False success | Reason |
| --- | --- | --- | --- | --- |
| B1 | fail | FAIL | 0 |  |
| B1 | long | PASS | 0 |  |
| B1 | longfail | FAIL | 0 |  |
| B1 | pipe | FAIL | 1 |  |
| B1 | multi | FAIL | 0 |  |
| B1 | gates | FAIL | 0 |  |
| B1 | gates_dry_run | PASS | 0 |  |
| B1 | nosuch | PASS | 0 |  |
| B1 | timeout | FAIL | 0 |  |
| B2 | tty=yes,claudecode=set,override=none | NOT_RUN | 0 | no_pty |
| B2 | tty=yes,claudecode=set,override=LADDER_AGENT=1 | NOT_RUN | 0 | no_pty |
| B2 | tty=yes,claudecode=set,override=LADDER_AGENT=0 | NOT_RUN | 0 | no_pty |
| B2 | tty=yes,claudecode=unset,override=none | NOT_RUN | 0 | no_pty |
| B2 | tty=yes,claudecode=unset,override=LADDER_AGENT=1 | NOT_RUN | 0 | no_pty |
| B2 | tty=yes,claudecode=unset,override=LADDER_AGENT=0 | NOT_RUN | 0 | no_pty |
| B2 | tty=no,claudecode=set,override=none | FAIL | 0 |  |
| B2 | tty=no,claudecode=set,override=LADDER_AGENT=1 | FAIL | 0 |  |
| B2 | tty=no,claudecode=set,override=LADDER_AGENT=0 | FAIL | 0 |  |
| B2 | tty=no,claudecode=unset,override=none | FAIL | 0 |  |
| B2 | tty=no,claudecode=unset,override=LADDER_AGENT=1 | FAIL | 0 |  |
| B2 | tty=no,claudecode=unset,override=LADDER_AGENT=0 | FAIL | 0 |  |
| B3 | long | FAIL | 0 |  |
| B3 | longfail150 | FAIL | 0 | no_log_path |
| B4 | pr-green | FAIL | 0 |  |
| B4 | pr-one-failed | FAIL | 0 |  |
| B4 | pr-review-pending | FAIL | 0 |  |
| B4 | pr-no-checks | FAIL | 0 |  |
| B4 | pr-log-missing | FAIL | 0 |  |
| B4 | pr-api-error | PASS | 0 |  |
| B5 | B5 | NOT_RUN | 0 | not_built_before_b5 |
| agent_questions | lab_gates | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | lab_gates_agent_mode | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | lab_longfail150 | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | pr_states | NOT_RUN | 0 | no_live_agent_run_in_b0 |
| agent_questions | tasks_b5 | NOT_RUN | 0 | no_live_agent_run_in_b0 |

| Row | Pass | Fail | Not run | False success |
| --- | --- | --- | --- | --- |
| B1 | 3 | 6 | 0 | 1 |
| B2 | 3 | 12 | 6 | 1 |
| B3 | 0 | 2 | 0 | 0 |
| B4 | 1 | 5 | 0 | 0 |
| B5 | 0 | 0 | 1 | 0 |
| overall | 4 | 19 | 12 | 1 |
