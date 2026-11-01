import io
import json
import shlex
import unittest
from unittest.mock import patch

from ladder.cli import main
from ladder.process import LadderError
from ladder.pr import summary


DOCTOR = {("git", "--version"): (0, "git version 2.50.0\n"),
          ("gh", "--version"): (0, "gh version 2.90.0\nrelease notes\n"),
          ("gh", "auth", "status"): (0, "ghp_MADE_UP_SECRET_DO_NOT_USE_1234567890")}

QUERY = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          isOutdated
          path
          line
          comments(first: 50) { nodes { author { login } body url } }
        }
      }
    }
  }
}"""
COMMAND = ('gh', 'api', 'graphql', '-F', 'owner={owner}', '-F', 'name={repo}',
           '-F', 'number=82', '-f', 'query=' + QUERY)
THREADS = '''{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":[
  {"isResolved":true,"isOutdated":true,"path":"src/b.rs","line":null,
   "comments":{"nodes":[{"author":{"login":"coderabbitai"},"body":"Old note","url":"https://x/1"}]}},
  {"isResolved":false,"isOutdated":false,"path":"src/a.rs","line":12,
   "comments":{"nodes":[
     {"author":{"login":"coderabbitai"},"body":"Check the error path","url":"https://x/2"},
     {"author":{"login":"Ahmed-Ahmed16"},"body":"Fixed in abc123","url":"https://x/3"}]}}
]}}}}}'''


class FakeRunner:
    def __init__(self, out, answers=None):
        self.out = out
        self.answers = {} if answers is None else answers
        self.commands = []

    def capture(self, argv):
        self.commands.append(argv)
        print("$ " + shlex.join(argv).replace("\n", "\\n"), file=self.out)
        answer = self.answers[tuple(argv)]
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    check = capture


class CliTests(unittest.TestCase):
    def invoke(self, argv, answers=None):
        out, err = io.StringIO(), io.StringIO()
        code = main(argv, FakeRunner(out, answers), out, err, load_config=lambda start: None)
        return code, out.getvalue(), err.getvalue()

    def test_help_lists_ticket_commands(self):
        for argv in ([], ["help"], ["-h"], ["--help"]):
            with self.subTest(argv=argv):
                code, out, err = self.invoke(argv)
                self.assertEqual((code, err), (0, ""))
                for command in ("help", "list", "doctor", "pr comments", "<task> [args]"):
                    self.assertIn(command, out)

    def test_help_and_pr_do_not_read_project_config(self):
        def broken_config(start):
            raise LadderError("broken config")

        for argv in (["help"], ["pr", "comments", "82"]):
            with self.subTest(argv=argv):
                out, err = io.StringIO(), io.StringIO()
                code = main(argv, FakeRunner(out, {COMMAND: THREADS}), out, err, broken_config)
                self.assertEqual((code, err.getvalue()), (0, ""))

    def test_setup_commands_have_help_without_config_or_writes(self):
        for name in ("init", "install-skill"):
            with self.subTest(name=name):
                code, out, err = self.invoke([name, "--help"])
                self.assertEqual((code, err), (0, ""))
                self.assertIn(name, out)

    def test_invalid_arguments_give_one_plain_error(self):
        for argv in (["nope"], ["pr"], ["pr", "comments", "bad"],
                     ["pr", "comments", "0"], ["pr", "comments", "9" * 5000], ["doctor", "--nope"]):
            with self.subTest(argv=argv):
                code, out, err = self.invoke(argv)
                self.assertEqual((code, out), (1, ""))
                self.assertEqual(len(err.splitlines()), 1)
                self.assertTrue(err.startswith("ladder: "))
                if "comments" in argv:
                    self.assertIn("PR number", err)

    def test_doctor_reports_all_checks_and_hides_auth_output(self):
        code, out, err = self.invoke(["doctor"], DOCTOR)
        self.assertEqual((code, err), (0, ""))
        for text in ("ok   git", "ok   gh", "ok   gh auth", "ok   Python",
                     "doctor: all checks passed"):
            self.assertIn(text, out)
        self.assertNotIn("MADE_UP_SECRET", out + err)
        self.assertNotIn("release notes", out)

    def test_doctor_fails_each_check_without_leaking_auth(self):
        cases = [(('git', '--version'), (1, 'broken'), 'git'),
                 (('gh', '--version'), LadderError('gh: not found'), 'gh: not found'),
                 (('gh', 'auth', 'status'), (1, DOCTOR[('gh', 'auth', 'status')][1]), 'gh auth'),
                 (None, None, 'Python')]
        for command, answer, label in cases:
            with self.subTest(label=label):
                answers = dict(DOCTOR)
                if command:
                    answers[command] = answer
                version = (3, 11, 0) if command is None else (3, 12, 10)
                with patch('sys.version_info', version):
                    code, out, err = self.invoke(['doctor'], answers)
                self.assertEqual((code, err), (1, ''))
                self.assertIn('FAIL ' + label, out)
                self.assertTrue(out.endswith('doctor: 1 check(s) failed\n'))
                self.assertNotIn('MADE_UP_SECRET', out + err)

    def test_unexpected_errors_are_plain_except_in_debug(self):
        for debug in ('0', '1'):
            with self.subTest(debug=debug), patch.dict('os.environ', LADDER_DEBUG=debug):
                code, out, err = self.invoke(['doctor'], {('git', '--version'): RuntimeError('broken\nsecond')})
                self.assertEqual(code, 1)
                self.assertIn('ladder: broken second', err)
                self.assertEqual('Traceback' in err, debug == '1')
                if debug == '0':
                    self.assertEqual(len(err.splitlines()), 1)

    def test_errors_and_versions_redact_tokens(self):
        secret = DOCTOR[('gh', 'auth', 'status')][1]
        for answer in (LadderError('failure ' + secret), RuntimeError('failure ' + secret), (0, 'failure ' + secret)):
            with self.subTest(answer=answer), patch.dict('os.environ', LADDER_DEBUG='1'):
                answers = dict(DOCTOR)
                answers[('git', '--version')] = answer
                code, out, err = self.invoke(['doctor'], answers)
                self.assertEqual(code, 0 if isinstance(answer, tuple) else 1)
                self.assertIn('failure [redacted]', out + err)
                self.assertNotIn(secret, out + err)

    def test_comments_keep_fields_hide_resolved_and_echo_command_first(self):
        code, out, err = self.invoke(['pr', 'comments', '82'], {COMMAND: THREADS})
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(out.splitlines()[0], '$ ' + shlex.join(COMMAND).replace('\n', '\\n'))
        self.assertIn('PR #82: 1 unresolved of 2 threads\n\nsrc/a.rs:12\n', out)
        self.assertIn('  coderabbitai:\n    Check the error path\n    https://x/2\n', out)
        self.assertIn('  Ahmed-Ahmed16:\n    Fixed in abc123\n    https://x/3\n', out)
        self.assertNotIn('src/b.rs', out)

    def test_all_shows_marks_and_sorts_unresolved_path_and_null_line_first(self):
        for answer in (THREADS, self.reordered_threads()):
            with self.subTest(answer=answer):
                code, out, err = self.invoke(['pr', 'comments', '82', '--all'], {COMMAND: answer})
                self.assertEqual((code, err), (0, ''))
                self.assertIn('src/b.rs [resolved] [outdated]\n  coderabbitai:\n    Old note\n    https://x/1', out)
                self.assertLess(out.index('src/a.rs:12'), out.index('src/b.rs [resolved]'))
                if answer != THREADS:
                    self.assertLess(out.index('\nsrc/a.rs\n'), out.index('src/a.rs:2'))
                    self.assertLess(out.index('src/a.rs:2'), out.index('src/a.rs:12'))
                    self.assertLess(out.index('src/a.rs:12'), out.index('\nsrc/z.rs\n'))

    def reordered_threads(self):
        answer = json.loads(THREADS)
        nodes = answer['data']['repository']['pullRequest']['reviewThreads']['nodes']
        nodes[1:1] = [dict(nodes[1], path='src/z.rs', line=None),
                      dict(nodes[1], line=2), dict(nodes[1], line=None)]
        return json.dumps(answer)

    def test_wrong_pr_and_bad_json_give_clear_errors(self):
        for answer, message in [('not JSON', 'bad JSON'),
                                ('{"data":{"repository":{"pullRequest":null}}}', 'PR number'),
                                ('{"data":{"repository":{"pullRequest":{"reviewThreads":{"nodes":{}}}}}}', 'PR number')]:
            with self.subTest(answer=answer):
                code, out, err = self.invoke(['pr', 'comments', '82'], {COMMAND: answer})
                self.assertEqual(code, 1)
                self.assertIn(message, err)
                self.assertEqual(len(err.splitlines()), 1)

    def test_empty_threads_and_missing_fields_match_rust_defaults(self):
        for nodes, expected in [([], 'PR #82: 0 unresolved of 0 threads\n'),
                                ([{'line': False, 'path': None, 'isResolved': 'true',
                                   'comments': {'nodes': [{'author': None, 'body': None, 'url': None}]}}],
                                 'PR #82: 1 unresolved of 1 threads\n\n\n  :\n    \n')]:
            with self.subTest(nodes=nodes):
                answer = json.dumps({'data': {'repository': {'pullRequest': {'reviewThreads': {'nodes': nodes}}}}})
                code, out, err = self.invoke(['pr', 'comments', '82'], {COMMAND: answer})
                self.assertEqual((code, err), (0, ''))
                self.assertTrue(out.endswith(expected))

    def test_default_summary_drops_markup_and_full_keeps_whole_body(self):
        body = ("<!-- coderabbit-ai-generated:v1 -->\n\n"
                '**<picture><img src="x.svg"></picture> Minor** · **Quick win**\n'
                '<details>\n<summary>Supported by static analysis</summary>\n'
                "<details><summary>inner</summary>sed -n '1,9p' file</details>\n</details>\n\n"
                '**Handle the empty list.**\n\nThe loop reads item 0 first.\nMore text.')
        answer = json.loads(THREADS)
        answer['data']['repository']['pullRequest']['reviewThreads']['nodes'][1]['comments']['nodes'][0]['body'] = body
        for flags in ([], ['--full']):
            with self.subTest(flags=flags):
                code, out, err = self.invoke(['pr', 'comments', '82'] + flags, {COMMAND: json.dumps(answer)})
                self.assertEqual((code, err), (0, ''))
                expected = body if flags else 'Minor · Quick win\nHandle the empty list.\nThe loop reads item 0 first.'
                self.assertIn('\n'.join('    ' + line for line in expected.splitlines()), out)
                self.assertEqual('More text.' in out, bool(flags))

    def test_summary_edges_keep_plain_text_and_hide_nested_logs(self):
        cases = [('', ''), (' \n a \n\n b\nc\nd', 'a\nb\nc'),
                 ('before<!-- hidden >\nmore -->after', 'beforeafter'),
                 ('before<details>outer<details>inner</details>tail</details>after', 'beforeafter'),
                 ('before<details>unclosed', 'before'), ('text < unfinished', 'text < unfinished'),
                 ('**keep** <b>words</b>', 'keep words')]
        for body, expected in cases:
            with self.subTest(body=body):
                self.assertEqual(summary(body), expected)

    def test_full_preserves_long_paths_links_and_commits_but_hides_quoted_secrets(self):
        answer = json.loads(THREADS)
        thread = answer['data']['repository']['pullRequest']['reviewThreads']['nodes'][1]
        path = 'src/review_thread_renderer_and_parser.py'
        url = 'https://example.test/a/review/thread/with/a/long/path'
        commit = '1234abcd' * 5
        thread['path'] = path
        thread['comments']['nodes'][0].update(url=url, body=commit + '\n{"password": "small private value"}\ntoken="two words"')
        code, out, err = self.invoke(['pr', 'comments', '82', '--full'], {COMMAND: json.dumps(answer)})
        self.assertEqual((code, err), (0, ''))
        for preserved in (path, url, commit):
            self.assertIn(preserved, out)
        self.assertIn('[redacted]', out)
        for secret in ('small private value', 'two words', 'words'):
            self.assertNotIn(secret, out)

    def test_error_secrets_include_escaped_and_unclosed_quotes_and_flags(self):
        cases = [(r'{"password": "start \"HIDDEN_SUFFIX"}', 'HIDDEN_SUFFIX'),
                 ('password="start HIDDEN_SUFFIX', 'HIDDEN_SUFFIX'),
                 ('--token MADE_UP_FLAG_SECRET', 'MADE_UP_FLAG_SECRET')]
        for message, secret in cases:
            with self.subTest(message=message):
                code, out, err = self.invoke(['pr', 'comments', '82'], {COMMAND: LadderError(message)})
                self.assertEqual(code, 1)
                self.assertIn('[redacted]', err)
                self.assertNotIn(secret, out + err)

    def test_comments_strip_hidden_controls_and_preserve_visible_unicode(self):
        # Cases: terminal controls and bidi marks; ordinary accents and Arabic.
        cases = [('\x1b[31mRed\x9b CSI \u202ebidi \u2066isolate\nNext\tline',
                  '[31mRed CSI bidi isolate\nNext\tline'),
                 ('caf\u00e9 na\u00efve\n\u0645\u0631\u062d\u0628\u0627',
                  'caf\u00e9 na\u00efve\n\u0645\u0631\u062d\u0628\u0627')]
        for body, expected in cases:
            for flags in ([], ['--full']):
                with self.subTest(body=body, flags=flags):
                    answer = json.loads(THREADS)
                    thread = answer['data']['repository']['pullRequest']['reviewThreads']['nodes'][1]
                    thread['comments']['nodes'][0]['body'] = body
                    code, out, err = self.invoke(['pr', 'comments', '82'] + flags,
                                                 {COMMAND: json.dumps(answer)})
                    self.assertEqual((code, err), (0, ''))
                    self.assertIn('\n'.join('    ' + line for line in expected.splitlines()), out)
                    for hidden in ('\x1b', '\x9b', '\u202e', '\u2066'):
                        self.assertNotIn(hidden, out + err)
