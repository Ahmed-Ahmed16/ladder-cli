"""Offline prompt and answer rules from the frozen B0 contract.

No function runs an agent or a command. Scores contain booleans only.
"""

from functools import cache
import json
from pathlib import Path
import re


@cache
def load_contract():
    return json.loads(Path(__file__).with_name("contracts.json").read_text(encoding="utf-8"))


def _question(question_id):
    questions = load_contract()["questions"]
    question = questions[question_id]
    while "same_as" in question:
        question = questions[question["same_as"]]
    return question


def build_prompt(question_id, task_id=None):
    """Return the prompt. Raise ValueError when task_id is missing for tasks_b5 or set for any other question."""
    question = _question(question_id)
    if question_id == "tasks_b5":
        tasks = {task["id"]: task for task in question["tasks"]}
        if task_id not in tasks:
            raise ValueError("tasks_b5 needs a frozen task id")
        return question["prompt"].replace("<task text>", tasks[task_id]["text"])
    if task_id is not None:
        raise ValueError("task_id applies only to tasks_b5")
    return question["prompt"]


def parse_answer(reply_text):
    """Read only the last nonempty line; scrub the marker in keys and values."""
    if not isinstance(reply_text, str) or not reply_text.strip():
        return None
    last_line = reply_text.rstrip().splitlines()[-1].strip()

    def reject_constant(value):
        raise ValueError("invalid JSON constant")

    try:
        answer = json.loads(last_line, parse_constant=reject_constant)
    except (ValueError, TypeError):
        return None
    if not isinstance(answer, dict):
        return None
    marker = load_contract()["privacy"]["fake_secret_marker"]

    def scrub(value):
        if isinstance(value, str):
            return value.replace(marker, "[redacted]")
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {scrub(key): scrub(item) for key, item in value.items()}
        return value

    return scrub(answer)


def normalise(key, value):
    """Normalise strings only; preserve numbers, booleans and other types."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if key in {"command", "next_command"}:
        if value.startswith("`") and value.endswith("`"):
            value = value.strip("`").strip()
        if value.startswith("$ "):
            value = value[2:].strip()
        if value.startswith("`") and value.endswith("`"):
            value = value.strip("`").strip()
    value = " ".join(value.split())
    return value.lower() if value.lower() in {"yes", "no", "unknown"} else value


def _answers(question_id, state_id=None):
    question = _question(question_id)
    if question_id == "pr_states":
        return question["states"][state_id]
    if question_id == "tasks_b5":
        for task in question["tasks"]:
            if task["id"] == state_id:
                return {"command": task["answer"]}
        raise ValueError("tasks_b5 needs a frozen task id")
    return question["answers"]


def score_answer(question_id, answer, state_id=None):
    """Return each frozen key's score. For tasks_b5, state_id is the task id.

    Gates require the exact error after trimming. The long failure needs its
    frozen error marker within the line. Extra answer keys do not earn points.
    """
    expected = _answers(question_id, state_id)
    answer = answer if isinstance(answer, dict) else {}
    scores = {}
    for key, truth in expected.items():
        value = answer.get(key)
        if type(value) is not type(truth):
            scores[key] = False
        elif key == "first_error_line" and question_id.startswith("lab_gates"):
            scores[key] = value.strip() == truth
        elif key == "first_error_line" and question_id == "lab_longfail150":
            scores[key] = "ERROR-synthetic-at-150" in value
        else:
            scores[key] = normalise(key, value) == normalise(key, truth)
    return scores


def is_false_green(state_id, answer):
    """A green=yes answer fails when frozen truth is no or unknown."""
    truth = _answers("pr_states", state_id)["green"]
    return (isinstance(answer, dict)
            and normalise("green", answer.get("green")) == "yes"
            and truth != "yes")


def _command_name(tokens):
    if tokens and tokens[0] == "&":
        tokens = tokens[1:]
    if not tokens:
        return ""
    return tokens[0].strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()


def count_piped_calls(commands):
    """Count commands once when a ladder pipeline reaches a listed filter.

    Quoted pipes and separate command chains do not join pipelines. This is a
    command-text check, not a shell interpreter; it does not expand aliases.
    """
    filters = {"head", "tail", "grep", "sed", "select-object", "select-string"}
    token_pattern = r'''"(?:`.|\\.|[^"\\])*"|'(?:''|[^'])*'|&&|\|\||[|;]|[^\s|;]+'''
    count = 0
    for command in commands:
        tokens = re.findall(token_pattern, command)
        segment = []
        ladder_seen = False
        matched = False
        for token in tokens + [";"]:
            if token not in {"|", ";", "&&", "||"}:
                segment.append(token)
                continue
            name = _command_name(segment)
            if ladder_seen and (name in filters or
                                (name == "select" and "-first" in [v.lower() for v in segment[1:]])):
                matched = True
            ladder_seen = ladder_seen or name in {"ladder", "ladder.exe"}
            segment = []
            if token != "|":
                ladder_seen = False
        count += int(matched)
    return count


def _score_keys(question_id):
    questions = load_contract()["questions"]
    if question_id in questions and question_id not in {"pr_states", "tasks_b5"}:
        return set(_answers(question_id))
    if question_id in questions["pr_states"]["states"]:
        return set(_answers("pr_states", question_id))
    for task in questions["tasks_b5"]["tasks"]:
        if question_id == task["id"]:
            return {"command"}
    return None


def run_passes(question_ids_scores, false_green=False, false_success=False):
    if false_green is not False or false_success is not False:
        return False
    if not isinstance(question_ids_scores, dict) or not question_ids_scores:
        return False
    for question_id, scores in question_ids_scores.items():
        if (not isinstance(scores, dict) or set(scores) != _score_keys(question_id)
                or not all(value is True for value in scores.values())):
            return False
    return True


def _build_id(build_row):
    builds = load_contract()["builds"]
    if isinstance(build_row, dict):
        build_id = build_row.get("id")
        if build_id is None:
            build_id = next((key for key, row in builds.items() if row == build_row), None)
    else:
        build_id = build_row
    if not isinstance(build_id, str) or build_id not in builds:
        raise ValueError("unknown frozen build row")
    return build_id


def arm_verdict(build_row, runs):
    """Return True when exactly 3 runs match the frozen row, else False. Return None for B6b, which has no pass minimum."""
    build_id = _build_id(build_row)
    if build_id == "B6b":
        return None
    question_id = load_contract()["builds"][build_id]["questions"]
    question = _question(question_id)
    if question_id == "pr_states":
        expected_ids = set(question["states"])
    elif question_id == "tasks_b5":
        expected_ids = {task["id"] for task in question["tasks"]}
    else:
        expected_ids = {question_id}
    if not isinstance(runs, list) or len(runs) != 3:
        return False
    for run in runs:
        if not isinstance(run, dict):
            return False
        answers = run.get("answers")
        if not isinstance(answers, dict) or set(answers) != expected_ids:
            return False
        if any(type(run.get(key)) is not int or run[key] < 0
               for key in ("tool_calls", "piped_calls")):
            return False
        if not run_passes(answers, run.get("false_green"), run.get("false_success", False)):
            return False
        if build_id == "B3a_B3b" and (run["tool_calls"] > 2 or run["piped_calls"] != 0):
            return False
        if build_id == "B4":
            calls = run.get("ladder_calls_by_state")
            if (not isinstance(calls, dict) or set(calls) != expected_ids
                    or any(type(value) is not int or value != 1 for value in calls.values())):
                return False
    return True


def session_plan(build_row):
    """Each prompt gets a session per repetition; JSON keys share that session."""
    build_id = _build_id(build_row)
    return {"B1": 3, "B2": 3, "B3a_B3b": 3, "B4": 18, "B5": 6, "B6b": None}[build_id]
