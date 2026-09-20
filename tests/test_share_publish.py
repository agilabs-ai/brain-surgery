import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.share_publish import Refused, collect, run_guards, validate_summary
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from render_report import summarize as summarize_comparison


class ExactPublicAllowlist(unittest.TestCase):
    def test_scan_summary_rejects_an_extra_private_field(self):
        data = {
            "schema_version": "brain-surgery-scan-public/0.1",
            "measured": True, "installed": 2, "reached": 1,
            "dormant": 1, "dormant_percent": 50,
            "load_attempts": 1, "confirmed_loads": 1, "failed_loads": 0,
            "sessions_analyzed": 1, "turns_analyzed": 2, "window_days": 30,
            "finding_counts": {}, "finding_groups": {},
            "finding_confidence_counts": {"confirmed": 0, "suspected": 0,
                                            "observation": 0},
            "resolved_loads_count": 0, "scope": "user",
            "harness_sessions_excluded": 0,
            "evaluation_performed": False, "change_status": "not_applied",
            "scan_complete": True, "private_skill_names": ["secret-skill"],
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(Refused, "outside.*public allowlist"):
                validate_summary(p, "scan")

    def test_current_scan_shape_is_accepted(self):
        data = {
            "schema_version": "brain-surgery-scan-public/0.1",
            "measured": True, "installed": 2, "reached": 1,
            "dormant": 1, "dormant_percent": 50,
            "load_attempts": 1, "confirmed_loads": 1, "failed_loads": 0,
            "sessions_analyzed": 1, "turns_analyzed": 2, "window_days": 30,
            "finding_counts": {}, "finding_groups": {},
            "finding_confidence_counts": {"confirmed": 0, "suspected": 0,
                                            "observation": 0},
            "resolved_loads_count": 0, "scope": "user",
            "harness_sessions_excluded": 0,
            "evaluation_performed": False, "change_status": "not_applied",
            "scan_complete": True,
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(json.dumps(data))
            self.assertEqual(validate_summary(p, "scan"), data)

    def test_summary_rejects_duplicate_top_level_keys(self):
        raw = json.loads((Path(__file__).parents[1] / "examples/demo-result.json").read_text())
        data = json.dumps(summarize_comparison(raw))
        data = data.replace('"model_family": ',
                            '"model_family":"PRIVATE_CUSTOMER_SECRET","model_family": ', 1)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(data)
            with self.assertRaisesRegex(Refused, "duplicate JSON key 'model_family'"):
                validate_summary(p, "comparison")

    def test_summary_rejects_duplicate_nested_keys(self):
        raw = json.loads((Path(__file__).parents[1] / "examples/demo-result.json").read_text())
        data = json.dumps(summarize_comparison(raw))
        data = data.replace('"label": ',
                            '"label":"PRIVATE_CUSTOMER_SECRET","label": ', 1)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(data)
            with self.assertRaisesRegex(Refused, "duplicate JSON key 'label'"):
                validate_summary(p, "comparison")

    def test_scan_summary_rejects_nested_private_fields(self):
        data = {
            "schema_version": "brain-surgery-scan-public/0.1",
            "measured": True, "installed": 2, "reached": 1,
            "dormant": 1, "dormant_percent": 50,
            "load_attempts": 1, "confirmed_loads": 1, "failed_loads": 0,
            "sessions_analyzed": 1, "turns_analyzed": 2, "window_days": 30,
            "finding_counts": {"shadowed": 1},
            "finding_groups": {"shadowed": {"count": 1, "confidence": "confirmed",
                                                "skill": "secret-skill"}},
            "finding_confidence_counts": {"confirmed": 1, "suspected": 0,
                                            "observation": 0},
            "resolved_loads_count": 0, "scope": "user",
            "harness_sessions_excluded": 0,
            "evaluation_performed": False, "change_status": "not_applied",
            "scan_complete": True,
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(Refused, "finding_groups.*outside"):
                validate_summary(p, "scan")

    def test_comparison_summary_rejects_nested_private_fields(self):
        raw = json.loads((Path(__file__).parents[1] / "examples/demo-result.json").read_text())
        data = summarize_comparison(raw)
        data["workflows"][0]["private_task"] = "customer-secret"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(Refused, r"workflows\[0\].*outside"):
                validate_summary(p, "comparison")

    def test_publisher_rejects_hand_edited_public_html(self):
        raw = json.loads((Path(__file__).parents[1] / "examples/demo-result.json").read_text())
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            from render_report import render
            render(raw, out)
            public = out / "public-report.html"
            public.write_text(public.read_text() + "<p>PRIVATE_CUSTOMER_NOT_ALLOWED</p>")
            with self.assertRaisesRegex(Refused, "exactly match"):
                run_guards(out, "comparison", collect(out, "comparison"))

    def test_comparison_summary_rejects_free_text_public_enums(self):
        raw = json.loads((Path(__file__).parents[1] / "examples/demo-result.json").read_text())
        data = summarize_comparison(raw)
        data["workflows"][0]["label"] = "PRIVATE_CUSTOMER_WORKFLOW"
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "summary.json"
            p.write_text(json.dumps(data))
            with self.assertRaisesRegex(Refused, "key/label"):
                validate_summary(p, "comparison")


if __name__ == "__main__":
    unittest.main()
