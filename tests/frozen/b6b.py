"""Replay frozen Claude sample needs without retaining child output."""

from collections import Counter
from contextlib import chdir
import json
from pathlib import Path
import sys
import tempfile

from .harness import make_lab, run_ladder
from .replay import FROZEN, UsageParser, offline_gh
from .scoring import extract_log_path, last_line_class


PROBES = {"pass": ["long"], "fail": ["longfail"], "err150": ["longfail150"],
          "gates": ["gates"], "info_list": ["list"],
          "info_doctor": ["doctor"], "info_help": ["help"]}
MARKERS = {"fail": "ERROR-database-not-found", "err150": "ERROR-synthetic-at-150",
           "gates": "ERROR-lint-failed"}


def select_sample(export_slots, sink_counts=None):
    if sink_counts is None or sink_counts == "all":
        return sorted(export_slots, key=lambda slot: slot["id"])
    remaining = dict(sink_counts)
    picked = []
    for slot in export_slots:
        sink = slot["sink"]
        if remaining.get(sink, 0) > 0:
            picked.append(slot)
            remaining[sink] -= 1
    if any(remaining.values()):
        raise ValueError("short_sample")
    return sorted(picked, key=lambda slot: slot["id"])


def run_probe(build_src, name, argv):
    with tempfile.TemporaryDirectory(prefix="ladder-b6b-") as scratch:
        scratch = Path(scratch)
        lab = make_lab(scratch / "lab")
        info = name.startswith("info_")
        env = offline_gh(scratch) if info else {}
        env["CLAUDECODE"] = "1"
        result = run_ladder(build_src, argv, lab, env_set=env,
                            env_remove=("LADDER_AGENT",))
        lines = [line.strip() for line in result.lines if line.strip()]
        log_read_ok = False
        with chdir(lab):
            log_path = extract_log_path(result.lines)
            if name in MARKERS and log_path is not None:
                read = run_ladder(build_src, ["log", str(log_path), "--head", "30"],
                                  lab, env_set=env, env_remove=("LADDER_AGENT",))
                log_read_ok = read.exit_code == 0 and bool(read.lines)
        expected = "fail_line" if name in MARKERS else "ok_line"
        marker = MARKERS.get(name)
        return {"exit_code": result.exit_code, "line_count": len(result.lines),
                "timed_out": bool(result.timed_out),
                "last_line_class": last_line_class(lines[-1] if lines else ""),
                "bounded": not result.timed_out and len(result.lines) <= 45,
                "outcome_last3": any(last_line_class(line) == expected for line in lines[-3:]),
                "error_seen": marker is not None and any(marker in line for line in result.lines),
                "log_path": log_path is not None, "log_read_ok": log_read_ok,
                "whole_log_visible": not info and "line 300 of 300" in result.lines}


def safe_probe(build_src, name, argv):
    try:
        return run_probe(build_src, name, argv)
    except Exception as error:
        return {"error_class": type(error).__name__}


def slot_verdict(slot, probes):
    row = {key: slot[key] for key in ("id", "sink", "ladder_sub", "need")}
    row.update(status="NOT_SCORABLE", met=None, met_loose=None, probe=None, reason="no_rule")
    sub, need = slot["ladder_sub"], slot["need"]
    if need in (None, "other"):
        row["reason"] = "need_other"
        return row
    if sub in ("add", "init", "pr", "transcript-audit", "transcript-audit-test"):
        row["reason"] = "sub_not_replayable"
        return row
    if sub in ("list", "doctor", "help"):
        names = ["info_" + sub]
    elif sub in ("gates", "other") and need in ("result", "error_line", "full_log"):
        names = (["gates"] if sub == "gates" else
                 ["pass", "fail"] if need == "result" else
                 ["err150"] if need == "error_line" else ["fail"])
    else:
        return row
    rows = [probes.get(name, {}) for name in names]
    met, loose = False, False
    broken = any(not probe or "error_class" in probe for probe in rows)
    if not broken:
        bounded = all(probe.get("bounded", False) for probe in rows)
        if sub in ("list", "doctor", "help"):
            loose = bounded and (sub != "doctor" or need != "result" or
                                 rows[0].get("last_line_class", "empty") != "empty")
            met = loose
        elif need == "result":
            loose = all(probe.get("outcome_last3", False) for probe in rows)
            met = bounded and loose
        elif need == "error_line":
            loose = bool(rows[0].get("error_seen") or rows[0].get("log_read_ok"))
            met = bounded and loose
        else:
            loose = bool(rows[0].get("whole_log_visible") or rows[0].get("log_read_ok"))
            met = bounded and bool(rows[0].get("log_path") and rows[0].get("log_read_ok"))
    row.update(status="SCORED", met=bool(met), met_loose=bool(loose),
               probe="+".join(names), reason="probe_error" if broken else "met" if met else "not_met")
    return row


def summarize(verdicts):
    total = len(verdicts)
    scored = sum(row["status"] == "SCORED" for row in verdicts)
    met = sum(row["met"] is True for row in verdicts)
    return {"slots": total, "scored": scored, "not_scorable": total - scored,
            "met": met, "met_loose": sum(row["met_loose"] is True for row in verdicts),
            "share_of_all": round(met / total, 3) if total else None,
            "share_of_scored": round(met / scored, 3) if scored else None,
            "reasons": dict(Counter(row["reason"] for row in verdicts))}


def markdown(builds):
    lines = ["| Build | Slots | Scored | Not scorable | Met | Met (loose) | Share of 46 | Share of scored |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    keys = ("slots", "scored", "not_scorable", "met", "met_loose",
            "share_of_all", "share_of_scored")
    for label, build in builds.items():
        values = [build["selected"][key] for key in keys]
        cells = [label.replace("|", "\\|").replace("\n", " ")]
        cells.extend("___" if value is None else str(value) for value in values)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = UsageParser(description="Replay frozen Claude pipe needs on source builds.")
    parser.add_argument("--export", dest="export_path", type=Path, required=True)
    parser.add_argument("--build", action="append", required=True, metavar="LABEL=SRC_DIR")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--md", type=Path)
    try:
        args = parser.parse_args(argv)
        export = json.loads(args.export_path.read_text(encoding="utf-8"))
        if not isinstance(export, dict) or export.get("format") != "ladder-case-export/1":
            return 2
        slots = export.get("slots")
        fields = {"id", "sink", "ladder_sub", "need", "fixture_id"}
        if not isinstance(slots, list) or any(
                not isinstance(slot, dict) or not fields <= slot.keys() or
                not isinstance(slot["sink"], str) for slot in slots):
            return 2
        counts = json.loads((FROZEN / "claude_sample.json").read_text(encoding="utf-8"))
        selected = select_sample(slots, counts["source"]["sink_counts"])
        if len(selected) != 46:
            return 2
        sources = {}
        for item in args.build:
            label, separator, folder = item.partition("=")
            source = Path(folder).resolve()
            if not separator or not label or not folder or label in sources or not (source / "ladder").is_dir():
                return 2
            sources[label] = source
        builds = {}
        for label, source in sources.items():
            probes = {name: safe_probe(source, name, argv) for name, argv in PROBES.items()}
            verdicts = [slot_verdict(slot, probes) for slot in selected]
            builds[label] = {"probes": probes, "selected": summarize(verdicts),
                             "all": summarize([slot_verdict(slot, probes) for slot in slots]),
                             "verdicts": verdicts}
        data = {"meta": {"export": args.export_path.name, "export_total": len(slots),
                         "sample_total": len(selected),
                         "selection": "first N per sink in export order"}, "builds": builds}
        args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if args.md is not None:
            args.md.write_text(markdown(builds), encoding="utf-8")
        return 0
    except (KeyError, TypeError) as error:
        sys.stderr.write(type(error).__name__ + "\n")
        return 2
    except (ValueError, OSError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
