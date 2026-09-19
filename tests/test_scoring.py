"""The scoring contract, and the property that makes multi-harness support real.

The integration risk is not that two adapters exist. It is that the same finished
work gets two different numbers depending on which harness produced it, at which
point "83%" means nothing and the report is worse than having no report.

So the load-bearing test here is the last class: identical evidence, arriving by
different routes, must score identically. Everything above it pins a rule that was
wrong in the version of this product that shipped a +72.2pp headline.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))

from scoring import (CONTRACT, INDICATOR, OUTCOME, UNCLASSIFIED,  # noqa: E402
                     classify, score_arm, score_run, score_task)


def chk(cid, kind, passed):
    return {'id': cid, 'class': kind, 'passed': passed}


class Classes(unittest.TestCase):
    def test_legacy_convention_is_not_silently_scored(self):
        """`convention` conflated two different things: checks testing something the
        user requires, and checks that only prove a skill fired. Mapping it to either
        scoring class would invent an answer, so it lands in `unclassified` and forces
        the question."""
        self.assertEqual(classify({'class': 'convention'}), UNCLASSIFIED)
        self.assertEqual(classify({'class': 'outcome'}), OUTCOME)
        self.assertEqual(classify({'class': 'indicator'}), INDICATOR)
        self.assertEqual(classify({'class': 'something-new'}), UNCLASSIFIED)


class RunScoring(unittest.TestCase):
    def test_a_task_fails_when_any_outcome_criterion_fails(self):
        """The headline is tasks meeting their criteria, not the fraction of checks
        passed.

        The ratio has to be lopsided or the test proves nothing: at two of three, a
        fraction rule and an all-must-pass rule both say fail, and the first version
        of this test used exactly that and let a check-fraction regression through.
        Nine cosmetic passes and one wrong calculation is the real case. It is 90% of
        checks and a failed task, and only one of those is the answer to "did this
        work".
        """
        checks = [chk(f'cosmetic{i}', 'outcome', True) for i in range(9)]
        checks.append(chk('the-number', 'outcome', False))
        r = score_run(checks)
        self.assertTrue(r['scorable'])
        self.assertFalse(r['task_passed'])
        self.assertEqual(r['checks']['outcome'], {'passed': 9, 'total': 10})

    def test_indicators_never_enter_the_score(self):
        """A skill firing is not a task succeeding. An indicator that failed must not
        drag down a run whose actual criteria were all met."""
        r = score_run([chk('did-the-job', 'outcome', True),
                       chk('skill-fired', 'indicator', False)])
        self.assertTrue(r['task_passed'])
        self.assertEqual(r['invocation'], {'fired': False, 'checked': 1})

    def test_a_task_with_only_indicators_is_not_scorable(self):
        """It measures whether our mechanism activated and nothing about outcomes.
        Scoring it would report a number for a question nobody asked."""
        r = score_run([chk('skill-fired', 'indicator', True)])
        self.assertFalse(r['scorable'])
        self.assertIsNone(r['task_passed'])
        self.assertIn('no outcome criteria', r['unscorable_reason'])

    def test_unclassified_checks_block_scoring_rather_than_being_dropped(self):
        """Quietly ignoring them would report a pass computed from half the checks,
        with nothing on the page saying so."""
        r = score_run([chk('did-the-job', 'outcome', True),
                       chk('house-format', 'convention', False)])
        self.assertFalse(r['scorable'])
        self.assertIsNone(r['task_passed'])
        self.assertIn('reclassified', r['unscorable_reason'])


class Aggregation(unittest.TestCase):
    def test_unscorable_runs_are_excluded_not_counted_as_failures(self):
        runs = [score_run([chk('a', 'outcome', True)]),
                score_run([chk('a', 'outcome', False)]),
                score_run([chk('only', 'indicator', True)])]
        t = score_task(runs)
        self.assertEqual((t['runs'], t['scored_runs'], t['passed_runs']), (3, 2, 1))
        self.assertEqual(t['rate'], 0.5)

    def test_arm_rate_is_task_macro(self):
        """One task run many times must not outvote one run twice, the same rule the
        headline metric already follows."""
        small = score_task([score_run([chk('a', 'outcome', True)])])
        large = score_task([score_run([chk('a', 'outcome', False)]) for _ in range(9)])
        self.assertEqual(score_arm([small, large])['pass_rate'], 50.0)

    def test_an_arm_with_nothing_scorable_reports_none_not_zero(self):
        empty = score_task([score_run([chk('only', 'indicator', True)])])
        a = score_arm([empty])
        self.assertIsNone(a['pass_rate'])
        self.assertEqual(a['scored_tasks'], 0)


class CrossAdapter(unittest.TestCase):
    """The integration property. This is the test the multi-harness plan rests on."""

    def test_identical_saved_outputs_score_identically_whatever_produced_them(self):
        """Two adapters, two evidence formats, one finished piece of work.

        A native runner hands back verdicts it already computed; our own runner hands
        back verdicts from checklib. If the underlying facts match, the contract must
        return the same number, or "83%" means something different per harness and the
        report is worse than no report.
        """
        # Same three criteria, same three verdicts, different shapes on the wire.
        from_ours = [{'id': 'archive-preserved', 'class': 'outcome', 'passed': True,
                      'detail': ''},
                     {'id': 'space-reclaimed', 'class': 'outcome', 'passed': True,
                      'detail': ''},
                     {'id': 'totals-correct', 'class': 'outcome', 'passed': False,
                      'detail': 'before_bytes is 0'}]
        from_native = [{'id': 'archive-preserved', 'class': 'outcome', 'passed': True,
                        'type': 'file_exists', 'judge_votes': None},
                       {'id': 'space-reclaimed', 'class': 'outcome', 'passed': True,
                        'type': 'regex', 'judge_votes': None},
                       {'id': 'totals-correct', 'class': 'outcome', 'passed': False,
                        'type': 'regex', 'judge_votes': None}]
        ours, native = score_run(from_ours), score_run(from_native)
        self.assertEqual(ours['task_passed'], native['task_passed'])
        self.assertEqual(ours['checks'], native['checks'])
        self.assertEqual(ours['scorable'], native['scorable'])

    def test_the_contract_is_versioned_so_a_change_is_visible(self):
        """Two implementations can only agree against a named contract. If it changes,
        stored results must be identifiable as scored under the old one."""
        r = score_run([chk('a', 'outcome', True)])
        self.assertEqual(r['contract'], CONTRACT)
        self.assertTrue(CONTRACT.startswith('brain-surgery-scoring/'))

    def test_extra_adapter_fields_cannot_change_the_score(self):
        """Adapters will carry their own metadata. Anything outside id/class/passed is
        explanation, and a scorer that reads it would drift between harnesses."""
        plain = score_run([chk('a', 'outcome', True), chk('b', 'outcome', False)])
        noisy = score_run([
            dict(chk('a', 'outcome', True), cost_usd=0.01, model='haiku', trace='...'),
            dict(chk('b', 'outcome', False), cost_usd=0.02, judge_votes=['PASS', 'FAIL'])])
        self.assertEqual(plain['task_passed'], noisy['task_passed'])
        self.assertEqual(plain['checks'], noisy['checks'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
