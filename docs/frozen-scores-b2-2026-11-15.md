| Row | Case | Status | False success | Reason |
| --- | --- | --- | --- | --- |
| B1 | fail | PASS | 0 |  |
| B1 | long | PASS | 0 |  |
| B1 | longfail | PASS | 0 |  |
| B1 | pipe | PASS | 0 |  |
| B1 | multi | PASS | 0 |  |
| B1 | gates | PASS | 0 |  |
| B1 | gates_dry_run | PASS | 0 |  |
| B1 | nosuch | PASS | 0 |  |
| B1 | timeout | PASS | 0 |  |
| B2 | tty=yes,claudecode=set,override=none | PASS | 0 |  |
| B2 | tty=yes,claudecode=set,override=LADDER_AGENT=1 | PASS | 0 |  |
| B2 | tty=yes,claudecode=set,override=LADDER_AGENT=0 | PASS | 0 |  |
| B2 | tty=yes,claudecode=unset,override=none | PASS | 0 |  |
| B2 | tty=yes,claudecode=unset,override=LADDER_AGENT=1 | PASS | 0 |  |
| B2 | tty=yes,claudecode=unset,override=LADDER_AGENT=0 | PASS | 0 |  |
| B2 | tty=no,claudecode=set,override=none | PASS | 0 |  |
| B2 | tty=no,claudecode=set,override=LADDER_AGENT=1 | PASS | 0 |  |
| B2 | tty=no,claudecode=set,override=LADDER_AGENT=0 | PASS | 0 |  |
| B2 | tty=no,claudecode=unset,override=none | PASS | 0 |  |
| B2 | tty=no,claudecode=unset,override=LADDER_AGENT=1 | PASS | 0 |  |
| B2 | tty=no,claudecode=unset,override=LADDER_AGENT=0 | PASS | 0 |  |
| B3 | long | FAIL | 0 |  |
| B3 | longfail150 | FAIL | 0 |  |
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
| B1 | 9 | 0 | 0 | 0 |
| B2 | 21 | 0 | 0 | 0 |
| B3 | 0 | 2 | 0 | 0 |
| B4 | 1 | 5 | 0 | 0 |
| B5 | 0 | 0 | 1 | 0 |
| overall | 22 | 7 | 6 | 0 |
