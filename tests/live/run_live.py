"""Live agent runs for ladder rows B3a/B3b, B4 and B5.

Each run is one fresh `claude -p` session in its own lab folder under RUNS.
Transcripts stay in RUNS, outside git. The scores file holds labels, booleans
and counts only. Every run bills the API; the harness stops past BUDGET_USD.

Usage: python -m tests.live.run_live <b3|b3noskill|b4|b5|all> [--runs N]
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import date

from tests.frozen.agent_questions import (
    arm_verdict, build_prompt, count_piped_calls, is_false_green, parse_answer, score_answer)
from tests.frozen.harness import make_lab
from tests.frozen.replay import gh_shims

REPO = Path(__file__).resolve().parents[2]
FROZEN = REPO / "tests" / "frozen"
RUNS = Path("D:/Ahmed-yzh/ladder-live-runs-2026-11-17")
SKILL = Path.home() / ".claude" / "skills" / "ladder" / "SKILL.md"
MODEL = "claude-sonnet-5-5"
BUDGET_USD = 5.0
RUN_BUDGET_USD = 0.75
RUN_TIMEOUT_S = 300
STATES = ["pr-green", "pr-one-failed", "pr-review-pending", "pr-no-checks",
          "pr-log-missing", "pr-api-error"]
TASKS = ["check_before_commit", "pr_green"]


class BudgetExceeded(RuntimeError):
    pass


def install_skill(lab):
    target = Path(lab) / ".claude" / "skills" / "ladder"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SKILL, target / "SKILL.md")


def read_stream(text):
    events = []
    for line in text.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    calls = []
    for event in events:
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    calls.append({"name": block["name"], "input": block.get("input", {})})
    result = next((e for e in events if e.get("type") == "result"), {})
    return calls, result


def run_session(label, lab, prompt, tools, env_extra=None):
    command = [shutil.which("claude"), "-p", "--model", MODEL, "--setting-sources", "project",
               "--output-format", "stream-json", "--verbose", "--no-session-persistence",
               "--max-budget-usd", str(RUN_BUDGET_USD), "--tools", ",".join(tools),
               "--allowedTools", ",".join(tools), "--strict-mcp-config",
               "--mcp-config", '{"mcpServers":{}}']
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.update(env_extra or {})
    done = subprocess.run(command, input=prompt, cwd=lab, env=env, text=True,
                          encoding="utf-8", errors="replace", capture_output=True,
                          timeout=RUN_TIMEOUT_S, check=False)
    (Path(lab).parent / f"{label}.jsonl").write_text(done.stdout, encoding="utf-8")
    if done.stderr:
        (Path(lab).parent / f"{label}.stderr.txt").write_text(done.stderr, encoding="utf-8")
    calls, result = read_stream(done.stdout)
    usage = result.get("usage", {})
    tokens = sum(usage.get(key, 0) for key in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    commands = [str(call["input"].get("command", "")) for call in calls
                if call["name"] in {"Bash", "PowerShell"}]
    return {
        "label": label, "exit": done.returncode, "is_error": bool(result.get("is_error", True)),
        "tool_calls": len(calls), "tool_names": [call["name"] for call in calls],
        "shell_calls": len(commands),
        "ladder_calls": sum(1 for command in commands if "ladder" in command),
        "piped_calls": count_piped_calls(commands),
        "tokens": tokens, "cost_usd": float(result.get("total_cost_usd") or 0.0),
        "answer": parse_answer(str(result.get("result", ""))),
    }


class Ledger:
    def __init__(self):
        self.cost = 0.0
        self.tokens = 0
        self.sessions = 0

    def add(self, run):
        self.cost += run["cost_usd"]
        self.tokens += run["tokens"]
        self.sessions += 1
        print(f"{run['label']}: calls={run['tool_calls']} piped={run['piped_calls']} "
              f"cost={run['cost_usd']:.4f} total={self.cost:.4f}", flush=True)
        if self.cost > BUDGET_USD:
            raise BudgetExceeded(f"total cost {self.cost:.2f} passed {BUDGET_USD}")


def fresh_lab(arm, label, with_skill=True):
    folder = RUNS / arm / label
    if folder.exists():
        shutil.rmtree(folder)
    lab = make_lab(folder / "lab")
    if with_skill:
        install_skill(lab)
    return lab


def b3(ledger, repetitions, with_skill=True):
    runs = []
    suffix = "" if with_skill else "-noskill"
    for rep in range(1, repetitions + 1):
        label = f"b3{suffix}-r{rep}"
        lab = fresh_lab("b3" + suffix, label, with_skill)
        run = run_session(label, lab, build_prompt("lab_longfail150"), ["Bash", "Read", "Skill"])
        ledger.add(run)
        scores = score_answer("lab_longfail150", run["answer"])
        runs.append({"answers": {"lab_longfail150": scores}, "tool_calls": run["tool_calls"],
                     "piped_calls": run["piped_calls"], "false_green": False, "detail": run})
    return runs


def b4(ledger, repetitions, states=STATES):
    runs = []
    with tempfile.TemporaryDirectory(prefix="ladder-live-bin-") as scratch:
        shim_env = gh_shims(Path(scratch) / "bin", FROZEN / "fake_gh.py")
        for rep in range(1, repetitions + 1):
            answers, ladder_calls, details, false_green = {}, {}, [], False
            tool_calls = piped = 0
            for state in states:
                label = f"b4-r{rep}-{state}"
                lab = fresh_lab("b4", label)
                env = dict(shim_env, FAKE_GH_STATE=str(FROZEN / "pr_states" / f"{state}.json"))
                run = run_session(label, lab, build_prompt("pr_states"),
                                  ["Bash", "Read", "Skill"], env)
                ledger.add(run)
                answers[state] = score_answer("pr_states", run["answer"], state)
                ladder_calls[state] = run["ladder_calls"]
                false_green = false_green or is_false_green(state, run["answer"])
                tool_calls += run["tool_calls"]
                piped += run["piped_calls"]
                details.append(run)
            runs.append({"answers": answers, "tool_calls": tool_calls, "piped_calls": piped,
                         "false_green": false_green, "ladder_calls_by_state": ladder_calls,
                         "detail": details})
    return runs


def b5(ledger, repetitions):
    runs = []
    for rep in range(1, repetitions + 1):
        answers, details, tool_calls, piped = {}, [], 0, 0
        for task in TASKS:
            label = f"b5-r{rep}-{task}"
            lab = fresh_lab("b5", label)
            run = run_session(label, lab, build_prompt("tasks_b5", task), ["Read", "Skill"])
            ledger.add(run)
            answers[task] = score_answer("tasks_b5", run["answer"], task)
            tool_calls += run["tool_calls"]
            piped += run["piped_calls"]
            details.append(run)
        runs.append({"answers": answers, "tool_calls": tool_calls, "piped_calls": piped,
                     "false_green": False, "detail": details})
    return runs


def b3_noskill(ledger, repetitions):
    return b3(ledger, repetitions, with_skill=False)


ROWS = {"B3a_B3b": ("b3", b3), "B3a_B3b_noskill": ("b3noskill", b3_noskill),
        "B4": ("b4", b4), "B5": ("b5", b5)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=["b3", "b3noskill", "b4", "b5", "all"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--state", choices=STATES)
    args = parser.parse_args(argv)
    ledger = Ledger()
    results = {}
    try:
        for build_id, (name, function) in ROWS.items():
            if args.row in {name, "all"}:
                only = [[args.state]] if args.state and name == "b4" else []
                runs = function(ledger, args.runs, *only)
                full = args.runs == 3 and not args.state
                results[build_id] = {"verdict": arm_verdict(build_id.removesuffix("_noskill"), runs) if full else None,
                                     "runs": runs}
    except BudgetExceeded as error:
        print(f"STOP: {error}", file=sys.stderr)
    tag = f"{args.row}-{args.state}" if args.state else args.row
    out = RUNS / f"scores-{tag}-{date.today().isoformat()}.json"
    out.write_text(json.dumps({"results": results, "cost_usd": round(ledger.cost, 4),
                               "tokens": ledger.tokens, "sessions": ledger.sessions},
                              indent=1, default=str), encoding="utf-8")
    print(f"cost={ledger.cost:.4f} tokens={ledger.tokens} sessions={ledger.sessions} -> {out}")


if __name__ == "__main__":
    main()
