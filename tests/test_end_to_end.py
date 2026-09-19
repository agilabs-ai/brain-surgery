"""The whole pipeline, on a machine built to have exactly one real problem.

Every other test here exercises one function. This one seeds a filesystem, writes
transcripts, and runs inspect -> analyze -> render the way SKILL.md tells the agent
to run them, because the failures that reached a real user were never in a single
function. They were in the seams: a name keyed one way in the inventory and another
in the transcript, an eval session counted as usage, a fix that existed in the JSON
and never reached the page.

The machine below has one genuine defect and a pile of things that look like defects
and are not. A pass means the report names the first and stays quiet about the rest.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'


def skill(path: Path, declared: str, body: str = 'body'):
    path.mkdir(parents=True, exist_ok=True)
    (path / 'SKILL.md').write_text(
        f'---\nname: {declared}\ndescription: d\n---\n\n{body}\n')


def use(uid, name, cwd, stamp, error=False):
    return [
        {'type': 'assistant', 'cwd': cwd, 'timestamp': stamp,
         'message': {'role': 'assistant', 'content': [
             {'type': 'tool_use', 'id': uid, 'name': 'Skill', 'input': {'skill': name}}]}},
        {'type': 'user', 'cwd': cwd, 'timestamp': stamp,
         'message': {'role': 'user', 'content': [
             {'type': 'tool_result', 'tool_use_id': uid,
              **({'is_error': True} if error else {}),
              'content': 'err' if error else 'loaded'}]}},
    ]


class WholePipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project = root / 'proj'
        self.project.mkdir()
        self.skills = root / 'skills'
        self.logs = root / 'logs'
        self.logs.mkdir()

        # THE ONE REAL DEFECT: two files claiming `wa`, with different contents.
        skill(self.skills / 'zzcollider', 'zzcollider', 'original')
        skill(root / 'other' / 'zzcollider', 'zzcollider', 'a different thing entirely')

        # Decoys, each a false positive this scan used to report.
        skill(self.skills / 'zztwin', 'zztwin', 'same')          # identical copy
        skill(root / 'mirror' / 'zztwin', 'zztwin', 'same')
        skill(self.skills / 'gstack-browse', 'browse')       # dir != declared name
        skill(self.skills / 'quiet', 'quiet')                # simply unused

        cwd = str(self.project)
        rows = []
        rows += use('u1', 'gstack-browse', cwd, '2026-09-18T10:00:00Z')
        rows += use('u2', 'quiet-neighbour', cwd, '2026-09-18T10:05:00Z')  # gap, loaded fine
        # An eval child in a temp workspace, loading a fixture skill.
        rows_h = use('u3', 'fixture-skill', '/private/tmp/harness/ws', '2026-09-18T10:10:00Z')
        (self.logs / 'real.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
        (self.logs / 'harness.jsonl').write_text('\n'.join(json.dumps(r) for r in rows_h))

    def tearDown(self):
        self.tmp.cleanup()

    def run_pipeline(self):
        out = Path(self.tmp.name) / 'out'
        insp, find = out / 'i.json', out / 'f.json'
        out.mkdir(exist_ok=True)
        for cmd in (
            [sys.executable, str(SCRIPTS / 'inspect_setup.py'),
             '--project', str(self.project), '--scope', 'user', '--explicit-log-scope',
             '--days', '365',
             '--skill-root', str(self.skills), '--skill-root', str(Path(self.tmp.name) / 'other'),
             '--skill-root', str(Path(self.tmp.name) / 'mirror'),
             '--logs', str(self.logs), '--out', str(insp)],
            [sys.executable, str(SCRIPTS / 'analyze_scan.py'), '--input', str(insp),
             '--out', str(find)],
            [sys.executable, str(SCRIPTS / 'render_scan.py'), '--input', str(find),
             '--out', str(out / 'report')],
        ):
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr[-500:])
        return (json.loads(insp.read_text()), json.loads(find.read_text()),
                (out / 'report' / 'local-scan.html').read_text(),
                (out / 'report' / 'public-scan.html').read_text())

    def test_the_one_real_defect_is_the_headline_and_the_decoys_are_not(self):
        insp, found, local, public = self.run_pipeline()

        confirmed = [f for f in found['findings'] if f.get('confidence') == 'confirmed']
        self.assertEqual([f['skill'] for f in confirmed], ['zzcollider'])
        self.assertEqual(confirmed[0]['code'], 'shadowed')
        self.assertIn('1 thing to fix', local)

        # Identical copies are an observation, not a defect.
        twin = [f for f in found['findings'] if f.get('skill') == 'zztwin']
        self.assertEqual([f['code'] for f in twin], ['duplicated'])

        # The eval child is gone, and its fixture skill is not a finding.
        self.assertEqual(insp['harness_sessions_excluded'], 1)
        self.assertNotIn('fixture-skill', json.dumps(found))

        # A skill whose directory and declared name differ is neither a gap nor
        # dormant: it was reached, under the name the host uses.
        self.assertNotIn('gstack-browse', insp['inventory_gap'])
        dormant = [f for f in found['findings'] if f['code'] == 'dormant'][0]
        self.assertNotIn('gstack-browse', dormant['evidence']['names'])
        self.assertNotIn('browse', dormant['evidence']['names'])

        # A gap that loaded cleanly is one coverage note, not a per-skill alarm.
        gap = [f for f in found['findings'] if f['code'] == 'inventory_gap']
        self.assertEqual(len(gap), 1)
        self.assertIsNone(gap[0]['skill'])
        self.assertEqual(gap[0]['evidence']['names'], ['quiet-neighbour'])

    def test_the_fix_reaches_the_page_and_stays_off_the_public_one(self):
        _, found, local, public = self.run_pipeline()
        fix = [f for f in found['findings'] if f.get('confidence') == 'confirmed'][0]['fix']
        self.assertTrue(fix.startswith('Diff them'))
        self.assertIn('class="fix"', local)
        self.assertIn('diff ', local)
        # Names chosen so a substring cannot match by accident: an earlier version
        # used `wa`, which is inside `.wrap` in the stylesheet, and the test failed
        # on its own CSS rather than on a leak.
        for secret in ('zzcollider', 'zztwin', self.tmp.name):
            self.assertNotIn(secret, public)


if __name__ == '__main__':
    unittest.main(verbosity=2)
