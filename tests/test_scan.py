"""Regression tests for the counting logic: inspect_setup.normalize/inspect and
analyze_scan.usage/analyze.

Every case here corresponds to a bug found by running the scan against real
transcripts. The product's claim is that the numbers are counted, not modelled,
so each test pins a counting rule that was once wrong in a way the user could
not see.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from inspect_setup import (LEGACY_PER_FILE_CAP, bare_skill_name, default_skill_roots,
                           inspect, inventory, normalize)
from analyze_scan import analyze, usage


def use_row(tool_use_id,skill,cwd=None):
    row={'type':'assistant','message':{'content':[{'type':'tool_use','name':'Skill','id':tool_use_id,'input':{'skill':skill}}]}}
    if cwd:row['cwd']=cwd
    return row


def result_row(tool_use_id,is_error=None,cwd=None):
    """is_error=None writes NO is_error key at all: the real success shape."""
    part={'type':'tool_result','tool_use_id':tool_use_id,'content':'Skill loaded'}
    if is_error is not None:part['is_error']=is_error
    row={'type':'user','message':{'content':[part]}}
    if cwd:row['cwd']=cwd
    return row


def names(events):return sorted(e['name'] for e in events)


class NormalizeTests(unittest.TestCase):
    def test_success_omits_is_error(self):
        """Bug 1: a matched result with no is_error key is a CONFIRMED load.
        Requiring `is_error is False` scored every real load as a zero."""
        s=normalize([use_row('a','seo'),result_row('a')],'claude','test')
        self.assertEqual(names(s['skill_attempts']),['seo'])
        self.assertEqual(names(s['confirmed_skill_loads']),['seo'])
        self.assertEqual(s['failed_skill_loads'],[])
        self.assertNotIn('is_error',json.dumps(s))

    def test_explicit_failure_is_a_failure_not_a_load(self):
        """Bug 2: the same shape with is_error true is a failed load only."""
        s=normalize([use_row('a','seo'),result_row('a',is_error=True)],'claude','test')
        self.assertEqual(names(s['skill_attempts']),['seo'])
        self.assertEqual(s['confirmed_skill_loads'],[])
        self.assertEqual(names(s['failed_skill_loads']),['seo'])

    def test_unmatched_attempt_is_neither(self):
        """Bug 3, the honesty property: a Skill call with no matching result
        anywhere (truncated transcript) is an attempt and nothing else.
        Absence of a result is not evidence of failure."""
        s=normalize([use_row('a','seo'),result_row('other-id')],'claude','test')
        self.assertEqual(names(s['skill_attempts']),['seo'])
        self.assertEqual(s['confirmed_skill_loads'],[])
        self.assertEqual(s['failed_skill_loads'],[])
        self.assertTrue(s['absence_is_not_zero'])

    def test_false_is_error_still_counts_as_a_load(self):
        s=normalize([use_row('a','seo'),result_row('a',is_error=False)],'claude','test')
        self.assertEqual(names(s['confirmed_skill_loads']),['seo'])
        self.assertEqual(s['failed_skill_loads'],[])


class InspectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.project=self.root/'proj';self.project.mkdir()
        self.logs=self.root/'logs';self.logs.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def write_jsonl(self,path,rows):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        return path

    def test_large_transcript_is_not_skipped(self):
        """Bug 4: a transcript past the old 3MB per-file cap must be read, not
        skipped. Refusing a whole file on size drops the busiest sessions,
        which are exactly the ones that carry the loads."""
        cwd=str(self.project)
        rows=[use_row('u1','heavy',cwd=cwd),result_row('u1',cwd=cwd)]
        rows+=[{'type':'assistant','cwd':cwd,'message':{'content':[]},'filler':'x'*8000} for _ in range(420)]
        path=self.write_jsonl(self.logs/'big-session.jsonl',rows)
        self.assertGreater(path.stat().st_size,LEGACY_PER_FILE_CAP)
        out=inspect(self.project,'claude',[],[self.logs])
        self.assertEqual([s['source'] for s in out['sessions']],[str(path.resolve())])
        self.assertEqual(names(out['sessions'][0]['confirmed_skill_loads']),['heavy'])
        self.assertGreater(out['limits']['bytes_read'],LEGACY_PER_FILE_CAP)

    def test_subagent_transcript_merges_into_parent(self):
        """Bug 5: <dir>/<sid>/subagents/*.jsonl is a fragment of session <sid>,
        not a session of its own. Its loads count; its session slot does not."""
        cwd=str(self.project)
        parent=self.write_jsonl(self.logs/'sess-1.jsonl',[use_row('p1','parent-skill',cwd=cwd),result_row('p1',cwd=cwd)])
        self.write_jsonl(self.logs/'sess-1'/'subagents'/'agent-x.jsonl',[use_row('s1','child-skill',cwd=cwd),result_row('s1',cwd=cwd)])
        out=inspect(self.project,'claude',[],[self.logs])
        self.assertEqual([s['source'] for s in out['sessions']],[str(parent.resolve())])
        session=out['sessions'][0]
        self.assertEqual(session['subagent_transcripts_merged'],1)
        self.assertEqual(names(session['confirmed_skill_loads']),['child-skill','parent-skill'])
        self.assertEqual(names(session['skill_attempts']),['child-skill','parent-skill'])

    def test_subagent_only_directory_produces_no_session(self):
        """A subagent file must never consume a session slot on its own, even
        when it does carry the project cwd and would otherwise qualify."""
        cwd=str(self.project)
        self.write_jsonl(self.logs/'sess-1'/'subagents'/'agent-x.jsonl',[use_row('s1','child-skill',cwd=cwd),result_row('s1',cwd=cwd)])
        self.assertEqual(inspect(self.project,'claude',[],[self.logs])['sessions'],[])


class AnalyzeTests(unittest.TestCase):
    def inspection(self,**over):
        data={'schema_version':'brain-surgery-inspection/0.3','created_at':'2026-01-01T00:00:00+00:00',
              'project':'/p','host':'claude','skills':[],'sessions':[],'inventory_gap':[],
              'limits':{'days':14,'max_sessions':30,'bytes_read':0},'warnings':[]}
        data.update(over);return data

    def test_zero_sessions_is_reported_honestly(self):
        """Bug 6: with nothing observed, the scan must not dress a percentage up
        as a measurement. Its actual contract: dormant_percent is None when
        nothing is installed, every count is 0, and coverage states that zero
        sessions were analyzed and that absence is not zero."""
        out=analyze(self.inspection())
        self.assertEqual(out['totals'],{'measured':False,'installed':0,'reached':0,'dormant':0,
                                        'loaded_outside_inventory':0,'dormant_percent':None,
                                        'load_attempts':0,'confirmed_loads':0,'failed_loads':0})
        self.assertEqual(out['coverage']['sessions_analyzed'],0)
        self.assertEqual(out['coverage']['turns_analyzed'],0)
        self.assertEqual(out['coverage']['invocation_coverage'],{})
        self.assertTrue(out['coverage']['absence_is_not_zero'])
        self.assertIn('not proof',out['coverage']['caveat'])
        self.assertEqual(out['most_used'],[])
        self.assertEqual([f['code'] for f in out['findings']],[])

    def test_skills_but_zero_sessions_emits_no_dormancy_headline(self):
        """100% dormant off zero sessions is arithmetic, not evidence. Installed
        skills with no transcript read must produce no dormancy finding and no
        percentage at all, only an explicit statement that nothing was measured."""
        out=analyze(self.inspection(skills=[{'name':'seo','path':'/a/SKILL.md'}]))
        self.assertFalse(out['totals']['measured'])
        self.assertIsNone(out['totals']['dormant_percent'])
        self.assertEqual(out['coverage']['sessions_analyzed'],0)
        self.assertTrue(out['coverage']['absence_is_not_zero'])
        self.assertEqual([f['code'] for f in out['findings']],['no_evidence'])
        finding=out['findings'][0]
        self.assertEqual(finding['evidence'],{'installed':1,'sessions_analyzed':0})
        self.assertIn('not evidence that your setup is healthy',finding['detail'])

    def test_one_session_restores_the_dormancy_headline(self):
        """The gate is the transcript, not the skill count: a single real session
        is enough for dormancy to become a measurement again."""
        out=analyze(self.inspection(skills=[{'name':'seo','path':'/a/SKILL.md'}],
                                    sessions=[{'session_id':'s1','turns':[],'skill_attempts':[],
                                               'confirmed_skill_loads':[],'failed_skill_loads':[]}]))
        self.assertTrue(out['totals']['measured'])
        self.assertEqual(out['totals']['dormant_percent'],100)
        dormant=[f for f in out['findings'] if f['code']=='dormant']
        self.assertEqual(len(dormant),1)
        self.assertEqual(dormant[0]['evidence'],{'installed':1,'reached':0,'dormant':1,'names':['seo']})

    def test_shadowed_names_both_paths(self):
        """Bug 7: one name in two inventory paths is a silent shadow. The
        finding must name both paths, because which one wins was not chosen."""
        out=analyze(self.inspection(skills=[{'name':'seo','path':'/b/seo/SKILL.md'},
                                            {'name':'seo','path':'/a/seo/SKILL.md'},
                                            {'name':'other','path':'/a/other/SKILL.md'}]))
        shadowed=[f for f in out['findings'] if f['code']=='shadowed']
        self.assertEqual(len(shadowed),1)
        self.assertEqual(shadowed[0]['skill'],'seo')
        self.assertEqual(shadowed[0]['evidence']['paths'],['/a/seo/SKILL.md','/b/seo/SKILL.md'])
        self.assertIn('2 places',shadowed[0]['title'])

    def test_usage_counts_each_kind_independently(self):
        """Bug 8: failures are counted, never derived as attempts minus loads.
        Here 3 attempts produced 1 load and 1 flagged failure; the third
        attempt was never resolved and belongs to neither."""
        sessions=[{'skill_attempts':[{'name':'seo'},{'name':'seo'},{'name':'seo'}],
                   'confirmed_skill_loads':[{'name':'seo'}],
                   'failed_skill_loads':[{'name':'seo'}]}]
        attempts,loads,failures=usage(sessions)
        self.assertEqual((attempts['seo'],loads['seo'],failures['seo']),(3,1,1))
        self.assertNotEqual(failures['seo'],attempts['seo']-loads['seo'])
        totals=analyze(self.inspection(sessions=sessions,skills=[{'name':'seo','path':'/a/SKILL.md'}]))['totals']
        self.assertEqual((totals['load_attempts'],totals['confirmed_loads'],totals['failed_loads']),(3,1,1))

    def test_usage_survives_an_end_to_end_normalize(self):
        """The two scripts must agree: what normalize records is what usage counts."""
        rows=[use_row('a','seo'),result_row('a'),use_row('b','seo'),result_row('b',is_error=True),use_row('c','seo')]
        attempts,loads,failures=usage([normalize(rows,'claude','test')])
        self.assertEqual((attempts['seo'],loads['seo'],failures['seo']),(3,1,1))

    def test_loads_from_outside_the_inventory_never_inflate_reached(self):
        """Bug 9: a skill can load from a root the scan never listed, so the set
        of loaded names is not a subset of the installed ones. 'reached' counts
        installed skills only, so reached + dormant equals installed exactly and
        a report that subtracts them cannot invent a category. The outside loads
        are reported beside the split, never folded into either side."""
        sessions=[{'skill_attempts':[{'name':'seo'},{'name':'ghost'}],
                   'confirmed_skill_loads':[{'name':'seo'},{'name':'ghost'}],
                   'failed_skill_loads':[]}]
        out=analyze(self.inspection(sessions=sessions,
                                    skills=[{'name':'seo','path':'/a/SKILL.md'},
                                            {'name':'idle','path':'/b/SKILL.md'}]))
        t=out['totals']
        self.assertEqual((t['installed'],t['reached'],t['dormant']),(2,1,1))
        self.assertEqual(t['reached']+t['dormant'],t['installed'])
        self.assertEqual(t['loaded_outside_inventory'],1)
        self.assertEqual(t['dormant_percent'],50)
        dormant=[f for f in out['findings'] if f['code']=='dormant'][0]
        self.assertEqual(dormant['evidence']['names'],['idle'])

    def test_a_truncated_scan_says_it_is_truncated(self):
        """Bug 10: the inspector warned that the read budget ran out and the
        warning was dropped before the report. A partial scan that looks complete
        is the same failure as a fabricated number: the reader cannot tell."""
        out=analyze(self.inspection(warnings=[
            'Total transcript read budget exhausted',
            'Skipped 21 oversized row(s), invocation trace may be incomplete: /Users/me/a.jsonl']))
        limits=out['scan_limits']
        self.assertFalse(limits['complete'])
        self.assertEqual(limits['reasons'],['read_budget_exhausted','oversized_rows_skipped'])
        self.assertIn('upper bound',limits['effect'])

    def test_a_complete_scan_is_not_flagged_partial(self):
        """The guard must stay quiet when nothing was missed, and a warning that
        does not mean unread transcripts must not raise a truncation flag."""
        clean=analyze(self.inspection())['scan_limits']
        self.assertTrue(clean['complete'])
        self.assertEqual(clean['reasons'],[])
        self.assertIsNone(clean['effect'])
        rooted=analyze(self.inspection(warnings=['Skill root not found: /Users/me/.claude/skills']))['scan_limits']
        self.assertTrue(rooted['complete'])
        self.assertEqual(rooted['reasons'],['skill_root_missing'])

    def test_an_unrecognized_warning_becomes_other_and_leaks_no_text(self):
        """Warning text carries paths and skill names. An unknown warning must
        degrade to a code, never travel as text into the categories."""
        secret='Something new broke in /Users/me/.claude/skills/li-post-fede'
        limits=analyze(self.inspection(warnings=[secret]))['scan_limits']
        self.assertEqual(limits['reasons'],['other'])
        self.assertTrue(limits['complete'])
        self.assertNotIn('li-post-fede',json.dumps(limits['reasons']))
        self.assertIn(secret,limits['warnings'])  # raw text stays, local report only


class InventoryRoots(unittest.TestCase):
    """The inventory is the denominator of the headline. A skill it cannot see is
    counted as capability the user does not have, which is the one direction the
    scan must never be wrong in silently."""

    def skill(self,path: Path,name: str):
        path.mkdir(parents=True,exist_ok=True)
        (path/'SKILL.md').write_text(f'---\nname: {name}\ndescription: d\n---\n\nbody\n')

    def test_a_symlinked_skill_directory_is_inventoried(self):
        """Bug: skill roots are commonly built from symlinks, one canonical copy
        linked into each host's directory. Skipping links skipped 116 of the 197
        entries in a real ~/.claude/skills and called daily-used skills dormant."""
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            self.skill(base/'canonical/seo','seo')
            root=base/'root';root.mkdir()
            (root/'seo').symlink_to(base/'canonical/seo')
            inv=inventory([root])
            self.assertEqual([s['name'] for s in inv['skills']],['seo'])

    def test_the_same_skill_linked_into_two_roots_is_counted_once(self):
        """A canonical skill linked into both host roots is one skill, not two,
        and must not surface as a name declared in two places."""
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            self.skill(base/'canonical/seo','seo')
            roots=[]
            for host in ('a','b'):
                root=base/host;root.mkdir()
                (root/'seo').symlink_to(base/'canonical/seo')
                roots.append(root)
            inv=inventory(roots)
            self.assertEqual(len(inv['skills']),1)

    def test_a_symlink_cycle_terminates(self):
        """Following links needs its own guard: a link back to an ancestor must
        end the walk rather than the session."""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'
            self.skill(root/'seo','seo')
            (root/'seo'/'loop').symlink_to(root)
            inv=inventory([root])
            self.assertEqual([s['name'] for s in inv['skills']],['seo'])

    def test_codex_root_is_not_scanned_for_a_claude_host(self):
        """Both hosts keep a root and a dual-host machine copies skills into each.
        Pooling them counts every shared skill twice: once as capability the
        scanned host never reached, once as a name declared in two places."""
        home=Path('/home/x');project=Path('/proj')
        claude=default_skill_roots(project,home,'claude')
        codex=default_skill_roots(project,home,'codex')
        self.assertNotIn(home/'.codex/skills',claude)
        self.assertIn(home/'.claude/skills',claude)
        self.assertIn(home/'.codex/skills',codex)
        self.assertNotIn(home/'.claude/skills',codex)

    def test_a_plugin_qualified_load_matches_its_bare_installed_name(self):
        """A plugin skill loads as `plugin:skill` and names itself `skill`. Counted
        apart, one skill's usage splits across two keys and the installed half
        reads as dormant."""
        self.assertEqual(bare_skill_name('bs-bsr-archive-lookup:bsr-archive-lookup'),
                         'bsr-archive-lookup')
        self.assertEqual(bare_skill_name('seo'),'seo')
        self.assertEqual(bare_skill_name(None),'')
        attempts,loads,failures=usage([{'confirmed_skill_loads':[
            {'name':'bs-x:seo'},{'name':'seo'}]}])
        self.assertEqual(loads['seo'],2)


if __name__=='__main__':unittest.main(verbosity=2)


class Precision(unittest.TestCase):
    """Rules that stop the scan reporting a correct setup as broken.

    Each pins a false positive found by running the checks against real trees. A
    diagnostic that cries wolf on a stranger's machine is worse than one that says
    nothing, because the first costs them time before they learn to ignore it.
    """

    def skill(self, path: Path, name: str):
        path.mkdir(parents=True, exist_ok=True)
        (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: d\n---\n\nbody\n')

    def analyze_with(self, skills):
        return analyze({'schema_version': 'brain-surgery-inspection/0.3',
                        'skills': skills, 'sessions': [{'turns': [1]}],
                        'inventory_gap': []})

    def codes(self, result, code):
        return [f for f in result['findings'] if f['code'] == code]

    def test_one_skill_symlinked_into_several_roots_is_not_a_collision(self):
        """The recommended layout is one canonical copy linked into each harness
        root. Reporting it as a name collision tells the user their correct setup
        is broken."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.skill(root / '.agents/skills/wa', 'wa')
            (root / '.claude/skills').mkdir(parents=True)
            (root / '.claude/skills/wa').symlink_to(root / '.agents/skills/wa')
            paths = [str(root / '.agents/skills/wa/SKILL.md'),
                     str(root / '.claude/skills/wa/SKILL.md')]
            result = self.analyze_with([{'name': 'wa', 'path': p} for p in paths])
        self.assertEqual(self.codes(result, 'shadowed'), [])

    def test_the_same_bare_name_in_different_plugins_is_not_a_collision(self):
        """Plugin skills load as `plugin:skill`. On a real marketplace cache
        `access` appeared in imessage, telegram and discord: three namespaced
        skills, none shadowing another."""
        paths = [f'/h/.claude/plugins/marketplaces/m/plugins/{p}/skills/access/SKILL.md'
                 for p in ('imessage', 'telegram', 'discord')]
        result = self.analyze_with([{'name': 'access', 'path': p} for p in paths])
        self.assertEqual(self.codes(result, 'shadowed'), [])

    def test_two_real_files_in_plain_roots_are_still_a_collision(self):
        """The guard must not swallow the true positive it was narrowed around."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.skill(root / 'a/use-tinyfish', 'use-tinyfish')
            self.skill(root / 'b/use-tinyfish', 'use-tinyfish')
            paths = [str(root / 'a/use-tinyfish/SKILL.md'),
                     str(root / 'b/use-tinyfish/SKILL.md')]
            result = self.analyze_with([{'name': 'use-tinyfish', 'path': p} for p in paths])
        self.assertEqual(len(self.codes(result, 'shadowed')), 1)

    def test_two_copies_inside_one_plugin_are_still_a_collision(self):
        base = '/h/.claude/plugins/marketplaces/m/plugins/one/skills'
        result = self.analyze_with([{'name': 'x', 'path': f'{base}/x/SKILL.md'},
                                    {'name': 'x', 'path': f'{base}/nested/x/SKILL.md'}])
        self.assertEqual(len(self.codes(result, 'shadowed')), 1)


class Buckets(unittest.TestCase):
    def test_a_confirmed_defect_outranks_a_higher_severity_suspected_one(self):
        """The ordering rule, tested where severity and confidence disagree.

        `load_failed` carries higher severity than `shadowed` and sounds worse, but
        it rests on an error in a past transcript that was never re-tested, while a
        collision is two files readable on disk right now. The reader can act on one
        today and can only guess about the other, so confidence leads.

        The first version of this test compared shadowed against dormant, where
        severity already gives the right answer, so it passed with the bucket rule
        deleted and pinned nothing.
        """
        result = analyze({'schema_version': 'brain-surgery-inspection/0.3',
                          'skills': [{'name': 'a', 'path': '/x/a/SKILL.md'},
                                     {'name': 'a', 'path': '/y/a/SKILL.md'}],
                          'sessions': [{'skill_attempts': [{'name': 'broken'}],
                                        'failed_skill_loads': [{'name': 'broken'}],
                                        'turns': [1]}],
                          'inventory_gap': []})
        order = [(f['code'], f['confidence']) for f in result['findings']]
        self.assertEqual(order[0], ('shadowed', 'confirmed'))
        self.assertIn(('load_failed', 'suspected'), order)
        self.assertLess(order.index(('shadowed', 'confirmed')),
                        order.index(('load_failed', 'suspected')))

    def test_dormancy_never_outranks_a_confirmed_defect(self):
        """Ordering by severity alone led the report with "163 of your skills were
        never used", which is not a defect. A fresh machine with five cleanly
        installed skills produced that finding and nothing else, which would have
        told a new user their setup was 80% broken when nothing was wrong."""
        result = analyze({'schema_version': 'brain-surgery-inspection/0.3',
                          'skills': [{'name': 'a', 'path': '/x/a/SKILL.md'},
                                     {'name': 'a', 'path': '/y/a/SKILL.md'},
                                     {'name': 'b', 'path': '/x/b/SKILL.md'}],
                          'sessions': [{'turns': [1]}], 'inventory_gap': []})
        self.assertEqual(result['findings'][0]['code'], 'shadowed')
        self.assertEqual(result['findings'][0]['confidence'], 'confirmed')
        dormant = [f for f in result['findings'] if f['code'] == 'dormant'][0]
        self.assertEqual(dormant['confidence'], 'observation')

    def test_one_root_cause_is_counted_once(self):
        """gmail-operations appeared twice on a real scan, as a failed load and as
        an inventory gap. One missing symlink, two symptoms. A defect count built
        by adding findings overstates the work."""
        result = analyze({'schema_version': 'brain-surgery-inspection/0.3',
                          'skills': [{'name': 'other', 'path': '/x/other/SKILL.md'}],
                          'sessions': [{'skill_attempts': [{'name': 'gmail-operations'}],
                                        'failed_skill_loads': [{'name': 'gmail-operations'}],
                                        'turns': [1]}],
                          'inventory_gap': ['gmail-operations']})
        hits = [f for f in result['findings'] if f.get('skill') == 'gmail-operations']
        self.assertEqual(len(hits), 1)
        self.assertIn('inventory gap', hits[0]['detail'])
