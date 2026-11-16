import unittest

from .b6b import select_sample, slot_verdict, summarize


def slot(need="result", sub="other"):
    return {"id": 1, "sink": "tail", "ladder_sub": sub, "need": need, "fixture_id": None}


class B6bTests(unittest.TestCase):
    def test_selection_takes_export_order_before_sorting(self):
        rows = [{"id": ident, "sink": sink} for ident, sink in
                [(9, "tail"), (8, "head"), (1, "tail"), (2, "head")]]
        self.assertEqual(select_sample(rows, {"tail": 1, "head": 1}), [rows[1], rows[0]])
        for counts in (None, "all"):
            with self.subTest(counts=counts):
                self.assertEqual([row["id"] for row in select_sample(rows, counts)], [1, 2, 8, 9])
        for counts in ({"tail": 3}, {"head": 3}, {"grep": 1}):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                select_sample(rows, counts)

    def test_slots_follow_need_and_subcommand_rules(self):
        good = {"bounded": True, "outcome_last3": True}
        cases = [
            ("other", "other", {}, "NOT_SCORABLE", None, None, "need_other"),
            (None, "add", {}, "NOT_SCORABLE", None, None, "need_other"),
            ("result", "add", {}, "NOT_SCORABLE", None, None, "sub_not_replayable"),
            ("count", "other", {}, "NOT_SCORABLE", None, None, "no_rule"),
            ("result", "list", {"info_list": good}, "SCORED", True, True, "met"),
            ("result", "list", {"info_list": {"bounded": False}}, "SCORED", False, False, "not_met"),
            ("result", "gates", {"gates": good}, "SCORED", True, True, "met"),
            ("result", "gates", {"gates": dict(good, bounded=False)},
             "SCORED", False, True, "not_met"),
            ("result", "gates", {"gates": dict(good, outcome_last3=False)},
             "SCORED", False, False, "not_met"),
            ("result", "other", {"pass": good, "fail": good}, "SCORED", True, True, "met"),
            ("result", "other", {"pass": good, "fail": dict(good, outcome_last3=False)},
             "SCORED", False, False, "not_met"),
            ("error_line", "other", {"err150": {"bounded": True, "log_read_ok": True}},
             "SCORED", True, True, "met"),
            ("full_log", "other", {"fail": {"bounded": True, "log_read_ok": True}},
             "SCORED", False, True, "not_met"),
            ("full_log", "other", {"fail": {"bounded": True, "log_read_ok": True, "log_path": True}},
             "SCORED", True, True, "met"),
            ("full_log", "other", {"fail": {"bounded": True, "log_path": True}},
             "SCORED", False, False, "not_met"),
            ("result", "other", {"pass": good, "fail": {"error_class": "OSError"}},
             "SCORED", False, False, "probe_error"),
            ("result", "doctor", {"info_doctor": {"bounded": True, "last_line_class": "empty"}},
             "SCORED", False, False, "not_met"),
        ]
        for need, sub, probes, status, met, loose, reason in cases:
            with self.subTest(need=need, sub=sub, probes=probes):
                row = slot_verdict(slot(need, sub), probes)
                self.assertEqual((row["status"], row["met"], row["met_loose"], row["reason"]),
                                 (status, met, loose, reason))
                self.assertEqual(set(row), {"id", "sink", "ladder_sub", "need", "status",
                                            "met", "met_loose", "probe", "reason"})

    def test_summary_counts_and_denominators(self):
        probes = {"info_list": {"bounded": True}}
        rows = [slot_verdict(slot("result", "list"), probes),
                slot_verdict(slot("result", "gates"),
                             {"gates": {"bounded": False, "outcome_last3": True}}),
                slot_verdict(slot("other"), {})]
        score = summarize(rows)
        self.assertEqual([score[key] for key in ("slots", "scored", "not_scorable", "met", "met_loose")],
                         [3, 2, 1, 1, 2])
        self.assertEqual((score["share_of_all"], score["share_of_scored"]), (0.333, 0.5))
        self.assertEqual(score["reasons"], {"met": 1, "not_met": 1, "need_other": 1})
        for rows in ([], [slot_verdict(slot("other"), {})]):
            with self.subTest(rows=rows):
                score = summarize(rows)
                self.assertIsNone(score["share_of_scored"])
                self.assertEqual(score["share_of_all"], 0.0 if rows else None)


if __name__ == "__main__":
    unittest.main()
