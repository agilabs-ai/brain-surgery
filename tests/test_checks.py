"""Regression tests for per-check scoring: eval/checklib, run_grid.parse_checks,
and to_result.class_rate.

Every case here pins a property that the single pass/fail bit got wrong. The
bit is why the no-skill arm of the published grid measured 1.4 percent: a task
that was done correctly and safely, but that skipped a filename the prompt
never mentioned, scored identically to one that deleted the only copy of the
archive. These tests exist so that cannot come back silently.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))

import checklib  # noqa: E402
from run_grid import parse_checks  # noqa: E402
from to_result import class_rate  # noqa: E402


def fresh():
    """checklib accumulates in a module global, so each case starts clean."""
    checklib._results = []


class Sections(unittest.TestCase):
    def test_a_failed_section_does_not_stop_the_ones_after_it(self):
        """The whole point. The old verifier called sys.exit(1) on the first
        failure, so every later check went unrun and unreported, and a task that
        got two things right and one wrong was indistinguishable from a task
        that got nothing right."""
        fresh()
        with checklib.section('first', 'outcome'):
            checklib.fail('nope')
        with checklib.section('second', 'outcome'):
            pass
        with checklib.section('third', 'convention'):
            checklib.fail('also nope')
        self.assertEqual([r['id'] for r in checklib._results], ['first', 'second', 'third'])
        self.assertEqual([r['passed'] for r in checklib._results], [False, True, False])

    def test_a_crashing_check_is_a_failed_check_not_a_lost_one(self):
        """An unexpected exception used to escape the verifier and take every
        later check with it, which reports a better score than was measured."""
        fresh()
        with checklib.section('boom', 'outcome'):
            raise KeyError('missing')
        with checklib.section('after', 'outcome'):
            pass
        self.assertFalse(checklib._results[0]['passed'])
        self.assertIn('KeyError', checklib._results[0]['detail'])
        self.assertTrue(checklib._results[1]['passed'])

    def test_an_unknown_class_is_rejected(self):
        fresh()
        with self.assertRaises(ValueError):
            with checklib.section('x', 'behaviour'):
                pass

    def test_a_duplicate_id_is_rejected(self):
        """Two sections sharing an id silently collapse two facts into one row."""
        fresh()
        with checklib.section('dup', 'outcome'):
            pass
        with self.assertRaises(ValueError):
            with checklib.section('dup', 'convention'):
                pass


class Emission(unittest.TestCase):
    def run_verifier(self, body: str, workspace: Path):
        script = Path(tempfile.mkdtemp()) / 'check.py'
        script.write_text(
            'import sys\nfrom pathlib import Path\n'
            f'sys.path.insert(0, {str(ROOT / "eval")!r})\n'
            'from checklib import fail, report as emit, section\n'
            f'ws = Path(sys.argv[1])\n{body}\nemit()\n')
        return subprocess.run([sys.executable, str(script), str(workspace)],
                              capture_output=True, text=True)

    def test_the_json_line_comes_first_and_parses(self):
        """run_grid reads only the first line, so anything printed for a human
        must come after it or scoring silently falls back to the single bit."""
        with tempfile.TemporaryDirectory() as d:
            p = self.run_verifier(
                "with section('a', 'outcome'):\n    pass\n"
                "with section('b', 'convention'):\n    fail('missing the house file')\n",
                Path(d))
        first = p.stdout.splitlines()[0]
        data = json.loads(first)
        self.assertEqual(data['totals']['outcome'], {'passed': 1, 'total': 1})
        self.assertEqual(data['totals']['convention'], {'passed': 0, 'total': 1})
        self.assertIn('FAIL b (convention)', p.stdout)

    def test_exit_code_keeps_its_old_meaning(self):
        """A runner that knows nothing about per-check scoring must keep scoring
        the task exactly as it did, or migrating one task would change the
        headline for every task."""
        with tempfile.TemporaryDirectory() as d:
            ok = self.run_verifier("with section('a', 'outcome'):\n    pass\n", Path(d))
            bad = self.run_verifier(
                "with section('a', 'outcome'):\n    pass\n"
                "with section('b', 'convention'):\n    fail('x')\n", Path(d))
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(bad.returncode, 1)

    def test_a_verifier_that_records_nothing_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.run_verifier('pass', Path(d))
        self.assertEqual(p.returncode, 2)


class Parsing(unittest.TestCase):
    def test_unmigrated_output_parses_as_none_not_as_zero(self):
        """The corpus migrates a task at a time. An old verifier printing 'ok'
        must read as 'no breakdown available', never as a breakdown in which
        every check failed."""
        self.assertIsNone(parse_checks('ok\n'))
        self.assertIsNone(parse_checks(''))
        self.assertIsNone(parse_checks('status.txt missing\n'))

    def test_a_foreign_json_line_is_refused(self):
        """Some verifier printing unrelated JSON must not be mistaken for a
        breakdown; the schema tag is the gate."""
        self.assertIsNone(parse_checks('{"checks": [{"id": "a"}]}'))
        self.assertIsNone(parse_checks('{"schema":"something-else/1","checks":[{"id":"a"}]}'))

    def test_a_migrated_line_parses(self):
        payload = json.dumps({'schema': 'brain-surgery-checks/0.1',
                              'checks': [{'id': 'a', 'class': 'outcome', 'passed': True}],
                              'totals': {'outcome': {'passed': 1, 'total': 1}}})
        self.assertEqual(parse_checks(payload + '\nFAIL something\n')['totals']
                         ['outcome']['total'], 1)


class ClassRates(unittest.TestCase):
    def cell(self, **kw):
        base = {'passed': 0, 'total': 1, 'loaded': 0, 'loaded_known': 0,
                'outcome_passed': 0, 'outcome_total': 0,
                'convention_passed': 0, 'convention_total': 0, 'graded_trials': 0}
        base.update(kw)
        return base

    def test_an_ungraded_corpus_returns_none_not_zero(self):
        """No migrated tasks means the rate is unknown. Reporting 0 would put
        the most alarming possible number on a page that measured nothing."""
        arm = {'t1': self.cell()}
        self.assertIsNone(class_rate(arm, ['t1'], 'outcome'))

    def test_tasks_with_no_checks_of_that_class_are_left_out(self):
        """A task that asserts no house convention says nothing about
        convention compliance. Scoring it zero would punish an arm for a check
        nobody wrote."""
        arm = {'has': self.cell(convention_passed=1, convention_total=2),
               'none': self.cell(outcome_passed=1, outcome_total=1)}
        self.assertEqual(class_rate(arm, ['has', 'none'], 'convention'), 50.0)

    def test_the_rate_is_a_task_macro_average_not_a_pooled_fraction(self):
        """One task with many checks must not outvote a task with few, which is
        the same rule the headline metric already follows."""
        arm = {'small': self.cell(outcome_passed=1, outcome_total=1),
               'large': self.cell(outcome_passed=0, outcome_total=9)}
        # Pooled would be 1/10 = 10%. Macro is the mean of 100% and 0%.
        self.assertEqual(class_rate(arm, ['small', 'large'], 'outcome'), 50.0)


class RealTask(unittest.TestCase):
    """The case that forced all of this, run against the real verifier."""

    def test_a_competent_no_skill_agent_scores_full_outcome_and_zero_convention(self):
        """disk-reclaim-report's prompt asks for scratch/ to be cleaned without
        touching what is queued for the archive. It never mentions a report.

        An agent that deletes the disposable caches, leaves the archive alone,
        and writes no report has done exactly what was asked. The old verifier
        scored that a total failure, and 24 tasks of that mislabel are what put
        the no-skill arm at 1.4 percent."""
        task = ROOT / 'eval' / 'tasks' / 'disk-reclaim-report'
        with tempfile.TemporaryDirectory() as d:
            ws = Path(d)
            for src in (task / 'workspace').rglob('*'):
                if src.is_file():
                    dst = ws / src.relative_to(task / 'workspace')
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
            for junk in list((ws / 'scratch' / 'build-cache').glob('*')) + \
                        list((ws / 'scratch' / 'old-logs').glob('*')):
                junk.unlink()
            p = subprocess.run([sys.executable, str(task / 'check.py'), str(ws)],
                               capture_output=True, text=True)
        totals = json.loads(p.stdout.splitlines()[0])['totals']
        self.assertEqual(totals['outcome']['passed'], totals['outcome']['total'])
        self.assertGreater(totals['outcome']['total'], 0)
        self.assertEqual(totals['convention']['passed'], 0)
        self.assertGreater(totals['convention']['total'], 0)
        # And the single bit still says fail, which is also true: the user would
        # still have to redo the write-up. Both facts, reported apart.
        self.assertEqual(p.returncode, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
