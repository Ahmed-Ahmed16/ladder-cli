import unittest

from ladder.mode import agent_mode


class AgentModeTests(unittest.TestCase):
    def test_environment_and_tty_table(self):
        cases = [
            ({}, False, (False, "no agent signal")),
            ({"CLAUDECODE": "1"}, False, (True, "CLAUDECODE set, no TTY")),
            ({"CLAUDECODE": "other"}, False, (True, "CLAUDECODE set, no TTY")),
            ({"CLAUDECODE": "1"}, True, (False, "CLAUDECODE set, but a TTY is present")),
            ({"CLAUDECODE": "1", "LADDER_AGENT": "0"}, False, (False, "LADDER_AGENT=0")),
            ({"CLAUDECODE": "1", "LADDER_AGENT": "0"}, True, (False, "LADDER_AGENT=0")),
            ({"LADDER_AGENT": "1"}, False, (True, "LADDER_AGENT=1")),
            ({"LADDER_AGENT": "1"}, True, (True, "LADDER_AGENT=1")),
            ({"CLAUDECODE": "1", "LADDER_AGENT": "1"}, True, (True, "LADDER_AGENT=1")),
            ({"CLAUDECODE": ""}, False, (False, "no agent signal")),
        ]
        for override in ("", "2", "yes"):
            cases.extend([({"LADDER_AGENT": override}, False, (False, "no agent signal")),
                          ({"LADDER_AGENT": override, "CLAUDECODE": "1"}, False,
                           (True, "CLAUDECODE set, no TTY")),
                          ({"LADDER_AGENT": override, "CLAUDECODE": "1"}, True,
                           (False, "CLAUDECODE set, but a TTY is present"))])
        for environ, tty, expected in cases:
            with self.subTest(environ=environ, tty=tty):
                self.assertEqual(agent_mode(environ, tty), expected)
