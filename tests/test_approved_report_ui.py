import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from render_report import render


class ApprovedReportUITests(unittest.TestCase):
    def raw(self):
        return json.loads((ROOT / 'examples/demo-result.json').read_text())

    def pages_for(self, raw):
        tmp = tempfile.TemporaryDirectory()
        render(raw, Path(tmp.name))
        out = Path(tmp.name)
        return tmp, (out / 'local-report.html').read_text(), (out / 'public-report.html').read_text()

    def render_demo(self):
        raw = json.loads((ROOT / 'examples/demo-result.json').read_text())
        tmp = tempfile.TemporaryDirectory()
        render(raw, Path(tmp.name))
        return tmp, Path(tmp.name)

    def test_approved_edge_comparison_structure_uses_real_metric(self):
        tmp, out = self.render_demo()
        try:
            page = (out / 'local-report.html').read_text()
            self.assertIn('Edge<span class="brand-divider"></span><span class="brand-product">Brain Surgery', page)
            self.assertIn('class="report-hero"', page)
            self.assertIn('class="public-graphic"', (out / 'public-report.html').read_text())
            self.assertIn('5/6 tasks passed', page)
            self.assertNotIn('requirements met', page.lower())
            self.assertNotIn('<div class="model-grid"', page)
        finally:
            tmp.cleanup()

    def test_public_report_has_no_private_evidence_or_plan(self):
        raw = json.loads((ROOT / 'examples/demo-result.json').read_text())
        raw['pairs'][0]['title'] = 'PRIVATE_CANARY_APPROVED_UI'
        raw['plan']['changes'][0]['patch_preview'] = 'PRIVATE_PATCH_APPROVED_UI'
        with tempfile.TemporaryDirectory() as d:
            render(raw, Path(d))
            public = (Path(d) / 'public-report.html').read_text()
            local = (Path(d) / 'local-report.html').read_text()
            self.assertNotIn('PRIVATE_CANARY_APPROVED_UI', public)
            self.assertNotIn('PRIVATE_PATCH_APPROVED_UI', public)
            self.assertIn('PRIVATE_PATCH_APPROVED_UI', local)
            self.assertNotIn('local-data', public)

    def test_report_preserves_tested_not_applied_semantics(self):
        tmp, out = self.render_demo()
        try:
            local = (out / 'local-report.html').read_text()
            public = (out / 'public-report.html').read_text()
            self.assertIn('Tested · not applied', local)
            self.assertIn('Your live setup is unchanged.', local)
            self.assertIn('Tested, not applied', public)
            self.assertNotIn('Surgery applied', local)
        finally:
            tmp.cleanup()

    def test_improved_copy_is_positive_only_without_regressions(self):
        tmp, local, public = self.pages_for(self.raw())
        try:
            self.assertIn('Better on this test.', public)
            self.assertIn('The tested setup did better', local)
            self.assertNotIn('Not safe to apply as-is.', local)
        finally:
            tmp.cleanup()

    def test_improved_with_regression_warns_instead_of_claiming_clean_win(self):
        raw = self.raw()
        raw['pairs'][0]['before'] = True
        raw['pairs'][0]['after'] = False
        tmp, local, public = self.pages_for(raw)
        try:
            self.assertIn('some work got worse', local)
            self.assertIn('Some work got worse.', public)
            self.assertIn('Not safe to apply as-is.', local)
            self.assertNotIn('The tested setup did better<br>', local)
        finally:
            tmp.cleanup()

    def test_unchanged_copy_does_not_claim_improvement(self):
        raw = self.raw()
        for pair in raw['pairs']:
            pair['after'] = pair['before']
        tmp, local, public = self.pages_for(raw)
        try:
            self.assertIn('did not change the measured result', local)
            self.assertIn('Same measured result.', public)
            self.assertIn('No measurable setup win', local)
            self.assertNotIn('up from', public)
        finally:
            tmp.cleanup()

    def test_degraded_copy_tells_user_to_keep_current_setup(self):
        raw = self.raw()
        for pair in raw['pairs']:
            pair['after'] = False
        tmp, local, public = self.pages_for(raw)
        try:
            self.assertIn('current setup performed better', local.lower())
            self.assertIn('tested setup fell from', public.lower())
            self.assertIn('Keep the current setup.', local)
            self.assertNotIn('Better at my work.', public)
        finally:
            tmp.cleanup()

    def test_insufficient_copy_has_no_comparison_score_or_optimism(self):
        raw = self.raw()
        raw['pairs'] = raw['pairs'][:1]
        tmp, local, public = self.pages_for(raw)
        try:
            self.assertIn('Not enough comparable work', local)
            self.assertIn('No comparison score yet.', public)
            self.assertIn('Missing comparisons are not zeros.', local)
            self.assertNotIn('up from', public)
            self.assertNotIn('Better at my work.', public)
            self.assertNotIn('class="public-workflow"', public)
            self.assertIn('Workflow percentages are withheld', local)
        finally:
            tmp.cleanup()

    def test_social_card_uses_edge_brand_and_matches_each_truthful_state(self):
        cases = []
        improved = self.raw()
        cases.append((improved, 'Better on this test.', '83<tspan', None))
        mixed = self.raw(); mixed['pairs'][0]['before'] = True; mixed['pairs'][0]['after'] = False
        cases.append((mixed, 'Some work got worse.', 'not safe to apply as-is', None))
        unchanged = self.raw()
        for pair in unchanged['pairs']: pair['after'] = pair['before']
        cases.append((unchanged, 'Same measured result.', 'Keep current setup', None))
        degraded = self.raw()
        for pair in degraded['pairs']: pair['after'] = False
        cases.append((degraded, 'Current setup.', 'Keep current setup', None))
        insufficient = self.raw(); insufficient['pairs'] = insufficient['pairs'][:1]
        cases.append((insufficient, 'No comparison score yet.', 'NOT SCORED', ' percent'))
        for raw, phrase, detail, forbidden in cases:
            with self.subTest(phrase=phrase), tempfile.TemporaryDirectory() as d:
                render(raw, Path(d))
                svg = (Path(d) / 'social-card.svg').read_text()
                self.assertIn('>Edge</text>', svg)
                self.assertIn('Brain Surgery by Edge.', svg)
                self.assertNotIn('agi labs', svg.lower())
                self.assertIn(phrase, svg)
                self.assertIn(detail, svg)
                if forbidden:
                    self.assertNotIn(forbidden, svg)

    def test_social_card_cannot_include_private_raw_fields_and_metadata_is_exact(self):
        raw = self.raw()
        raw['pairs'][0]['title'] = 'PRIVATE_SOCIAL_CANARY'
        raw['plan']['changes'][0]['patch_preview'] = 'PRIVATE_SOCIAL_PATCH'
        with tempfile.TemporaryDirectory() as d:
            render(raw, Path(d))
            svg = (Path(d) / 'social-card.svg').read_text()
            public = (Path(d) / 'public-report.html').read_text()
            self.assertNotIn('PRIVATE_SOCIAL_CANARY', svg)
            self.assertNotIn('PRIVATE_SOCIAL_PATCH', svg)
            self.assertIn('<meta property="og:image" content="social-card.svg">', public)

    def test_primary_action_always_has_a_real_target(self):
        raw = self.raw()
        raw['plan']['changes'] = []
        tmp, local, _ = self.pages_for(raw)
        try:
            self.assertNotIn('<button class="btn btn-dark" data-action="surgery"', local)
            self.assertIn('href="#report-method"', local)
            self.assertIn('id="report-method"', local)
        finally:
            tmp.cleanup()

    def test_private_task_evidence_is_visible_and_public_export_is_utf8_safe(self):
        tmp, local, public = self.pages_for(self.raw())
        try:
            self.assertIn('href="#report-tests">View tests</a>', local)
            self.assertIn('id="report-tests"', local)
            self.assertIn('TEST EVIDENCE · LOCAL ONLY', local)
            self.assertIn('Uint8Array.from(atob(', local)
            self.assertNotIn('id="report-tests"', public)
        finally:
            tmp.cleanup()

    def test_private_evidence_shows_invalid_reason_checks_invocation_and_empty_state(self):
        raw = self.raw()
        raw['pairs'][0]['checks'] = {
            'before': [{'passed': False}], 'after': [{'passed': True}],
        }
        raw['pairs'][1] = {
            'task_id': 'invalid-2', 'workflow': 'writing', 'title': 'Incomplete private task',
            'valid': False, 'invalid_reason': 'budget_exhausted',
            'invocation': {'eligible': True, 'before': None, 'after': None},
        }
        tmp, local, _ = self.pages_for(raw)
        try:
            self.assertIn('before: 0/1 checks; after: 1/1 checks; skill: not loaded → loaded', local)
            self.assertIn('Excluded: budget_exhausted', local)
            self.assertIn('1 invalid pair excluded', local)
        finally:
            tmp.cleanup()
        raw['pairs'] = []
        tmp, local, _ = self.pages_for(raw)
        try:
            self.assertIn('href="#report-tests"', local)
            self.assertIn('id="report-tests"', local)
            self.assertIn('No task pairs were recorded.', local)
        finally:
            tmp.cleanup()

    def test_renderer_tightens_existing_output_directory_and_private_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / 'report'
            out.mkdir(mode=0o755)
            render(self.raw(), out)
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            self.assertEqual((out / 'local-report.html').stat().st_mode & 0o777, 0o600)

    def test_workflow_rows_are_not_dead_controls_and_model_label_is_allowlisted(self):
        raw = self.raw()
        tmp, local, public = self.pages_for(raw)
        try:
            self.assertNotIn('data-workflow=', local)
            self.assertNotIn('<button class="workflow-line"', local)
            self.assertIn('<div class="workflow-line">', local)
        finally:
            tmp.cleanup()
        raw['stronger_model'] = 'PRIVATE_MODEL_CANARY'
        raw['model_lift'] = 10
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError, 'stronger_model'):
            render(raw, Path(d))
        degraded = self.raw()
        for pair in degraded['pairs']: pair['after'] = False
        tmp, local, _ = self.pages_for(degraded)
        try:
            self.assertNotIn('<button class="btn btn-dark" data-action="surgery"', local)
            self.assertIn('href="#report-method"', local)
        finally:
            tmp.cleanup()


if __name__ == '__main__':
    unittest.main()
