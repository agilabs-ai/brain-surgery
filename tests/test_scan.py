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
                           detect_host, host_bundled, inspect, inventory,
                           is_harness_session, normalize)
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


class NameKeying(unittest.TestCase):
    """The host addresses a skill by its directory name; the inventory used to key
    on the declared one. 13 skills on a real machine declare a different name than
    their directory, and each produced two false findings from that one mismatch."""

    def write(self, path: Path, declared: str):
        path.mkdir(parents=True, exist_ok=True)
        (path / 'SKILL.md').write_text(f'---\nname: {declared}\ndescription: d\n---\n\nbody\n')

    def test_a_skill_is_keyed_on_its_directory_and_answers_to_both_names(self):
        """`~/.claude/skills/gstack-browse/SKILL.md` declares `browse`. The
        transcript recorded a load of `gstack-browse`, the inventory held `browse`,
        and the scan reported the same skill as missing from disk AND as dormant."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.write(root / 'gstack-browse', 'browse')
            inv = inventory([root])
        entry = inv['skills'][0]
        self.assertEqual(entry['name'], 'gstack-browse')
        self.assertEqual(entry['declared_name'], 'browse')
        self.assertEqual(entry['aliases'], ['browse', 'gstack-browse'])

    def test_a_matching_directory_and_declared_name_records_no_alias(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.write(root / 'pdf', 'pdf')
            entry = inventory([root])['skills'][0]
        self.assertEqual(entry['name'], 'pdf')
        self.assertIsNone(entry['declared_name'])
        self.assertEqual(entry['aliases'], ['pdf'])


class HarnessSessions(unittest.TestCase):
    """SKILL.md requires excluding evaluation sessions from usage evidence. It was
    never implemented, and the grid harness's own agent children accounted for 13 of
    22 findings on a real scan: the scan reported its own fixtures as user faults."""

    def test_a_session_in_a_temp_workspace_is_a_harness_run(self):
        self.assertTrue(is_harness_session('/private/tmp/claude-501/x/workspace'))
        self.assertTrue(is_harness_session('/var/folders/nz/abc/T/bs-integration-1'))

    def test_a_session_in_a_real_project_is_not(self):
        self.assertFalse(is_harness_session('/Users/someone/Projects/thing'))
        self.assertFalse(is_harness_session(None))

    def test_a_directory_merely_named_tmp_is_not_a_temp_root(self):
        self.assertFalse(is_harness_session('/Users/someone/tmp/project'))

    def test_inspect_actually_drops_the_harness_session(self):
        """The helper being correct is not the same as inspect() calling it. The
        first version of this class tested only the predicate, so deleting the
        wiring from inspect() broke nothing and the guard pinned nothing.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            project = root / 'proj'
            (project).mkdir()
            logs = root / 'logs'
            logs.mkdir()
            # One real session in the project, one eval child in a temp workspace
            # outside it, each loading a different skill.
            real = [use_row('u1', 'real-skill', cwd=str(project)),
                    result_row('u1', cwd=str(project))]
            harness_cwd = '/private/tmp/claude-501/xyz/workspace'
            fake = [use_row('u2', 'bsr-rollup-brief', cwd=harness_cwd),
                    result_row('u2', cwd=harness_cwd)]
            for name, rows in (('real.jsonl', real), ('harness.jsonl', fake)):
                (logs / name).write_text('\n'.join(json.dumps(r) for r in rows))
            out = inspect(project, 'claude', [root / 'skills'], [logs],
                          days=3650, explicit=True, scope='user')
        self.assertEqual(out['harness_sessions_excluded'], 1)
        used = {a['name'] for s in out['sessions'] for a in s['skill_attempts']}
        self.assertIn('real-skill', used)
        self.assertNotIn('bsr-rollup-brief', used)
        # And the harness skill must not resurface as a gap, which is exactly how
        # the fixtures reached the user's report.
        self.assertNotIn('bsr-rollup-brief', out['inventory_gap'])

    def test_scanning_a_project_under_a_temp_root_still_counts_its_sessions(self):
        """Scanning a project that happens to live in a temp directory is a real
        thing to do, and those sessions are in scope by the user's own choice."""
        self.assertFalse(is_harness_session('/private/tmp/proj/src',
                                            project=Path('/private/tmp/proj')))
        self.assertTrue(is_harness_session('/private/tmp/elsewhere/ws',
                                           project=Path('/private/tmp/proj')))


class Reverification(unittest.TestCase):
    def test_a_failure_that_now_resolves_is_reported_as_resolved_not_as_broken(self):
        """A transcript error is evidence about the moment it happened. Both
        gmail-operations and agentwallet-credential-ops failed every attempt in the
        window and resolve on disk today, because the missing symlinks were added
        afterwards. Reporting them as current faults sends the user to fix something
        already fixed."""
        result = analyze({
            'schema_version': 'brain-surgery-inspection/0.3',
            'skills': [{'name': 'gmail-operations', 'path': '/x/gmail-operations/SKILL.md',
                        'aliases': ['gmail-operations']}],
            'sessions': [{'skill_attempts': [{'name': 'gmail-operations'}],
                          'failed_skill_loads': [{'name': 'gmail-operations'}],
                          'turns': [1]}],
            'inventory_gap': []})
        self.assertEqual(result['resolved_since'], ['gmail-operations'])
        self.assertEqual([f for f in result['findings'] if f['code'] == 'load_failed'], [])

    def test_a_failure_that_still_does_not_resolve_is_still_reported(self):
        result = analyze({
            'schema_version': 'brain-surgery-inspection/0.3',
            'skills': [{'name': 'other', 'path': '/x/other/SKILL.md', 'aliases': ['other']}],
            'sessions': [{'skill_attempts': [{'name': 'ghost'}],
                          'failed_skill_loads': [{'name': 'ghost'}], 'turns': [1]}],
            'inventory_gap': []})
        self.assertEqual(result['resolved_since'], [])
        self.assertEqual(len([f for f in result['findings'] if f['code'] == 'load_failed']), 1)


class IdenticalCopies(unittest.TestCase):
    """Every collision on the first real machine scanned was the same skill copied,
    not symlinked, into a second harness root. Byte-identical, so whichever one the
    host loads the behaviour is the same. Calling that a defect invents work and
    teaches the reader to ignore the scan."""

    def run_with(self, digests):
        return analyze({'schema_version': 'brain-surgery-inspection/0.3',
                        'skills': [{'name': 'ax-browser-broker', 'aliases': ['ax-browser-broker'],
                                    'path': f'/root{n}/ax-browser-broker/SKILL.md',
                                    'skill_md_sha256': d}
                                   for n, d in enumerate(digests)],
                        'sessions': [{'turns': [1]}], 'inventory_gap': []})

    def test_identical_copies_are_an_observation_not_a_defect(self):
        result = self.run_with(['same', 'same'])
        hit = [f for f in result['findings'] if f['skill'] == 'ax-browser-broker'][0]
        self.assertEqual(hit['code'], 'duplicated')
        self.assertEqual(hit['confidence'], 'observation')
        self.assertTrue(hit['evidence']['identical'])

    def test_copies_that_differ_are_still_a_confirmed_collision(self):
        """The guard must not swallow the case it was narrowed around: two files
        that really do differ means one wins and the other never runs."""
        result = self.run_with(['one', 'other'])
        hit = [f for f in result['findings'] if f['skill'] == 'ax-browser-broker'][0]
        self.assertEqual(hit['code'], 'shadowed')
        self.assertEqual(hit['confidence'], 'confirmed')
        self.assertFalse(hit['evidence']['identical'])

    def test_a_missing_digest_is_treated_as_differing(self):
        """Absent evidence must not be read as evidence of sameness, which would
        downgrade a real collision on the strength of a field nobody filled in."""
        result = self.run_with(['one', None])
        hit = [f for f in result['findings'] if f['skill'] == 'ax-browser-broker'][0]
        self.assertEqual(hit['code'], 'shadowed')


class CodexInvocation(unittest.TestCase):
    """Codex has no Skill tool. A skill is loaded by the agent reading its SKILL.md
    through the shell, and without parsing that the scan saw zero invocations across
    78,515 events and reported 214 of 214 skills dormant on a machine where 84 were
    in active use."""

    def rollout(self, path: Path, commands):
        rows = []
        for n, cmd in enumerate(commands):
            rows.append({'type': 'response_item', 'timestamp': f'2026-09-1{n}T10:00:00Z',
                         'payload': {'type': 'custom_tool_call', 'name': 'exec',
                                     'input': cmd}})
        path.write_text('\n'.join(json.dumps(r) for r in rows))

    def scan(self, commands):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            logs = root / 'logs'
            logs.mkdir()
            self.rollout(logs / 'rollout-1.jsonl', commands)
            return inspect(root / 'proj', 'codex', [root / 'skills'], [logs],
                           days=3650, explicit=True, scope='user')

    def loaded(self, out):
        return {a['name'] for s in out['sessions'] for a in s['confirmed_skill_loads']}

    def test_reading_a_skill_file_through_the_shell_counts_as_a_load(self):
        out = self.scan(['{"cmd":"sed -n 1,240p /Users/x/.codex/skills/workplan/SKILL.md"}'])
        self.assertEqual(self.loaded(out), {'workplan'})

    def test_a_skill_md_outside_a_skills_directory_is_not_a_load(self):
        """Matching any SKILL.md anywhere would count somebody editing a file, or a
        harness reading its own fixtures, as using the skill. That is exactly the
        bug that put 13 eval fixtures into a user's report."""
        out = self.scan(['{"cmd":"cat /Users/x/Projects/thing/docs/SKILL.md"}',
                         '{"cmd":"vim ./SKILL.md"}'])
        self.assertEqual(self.loaded(out), set())

    def test_the_same_read_twice_in_one_event_is_one_load(self):
        out = self.scan(['{"cmd":"cat a/skills/wa/SKILL.md a/skills/wa/SKILL.md"}'])
        self.assertEqual(len([a for s in out['sessions']
                              for a in s['confirmed_skill_loads']]), 1)

    def test_several_skills_in_one_command_are_all_counted(self):
        out = self.scan(['{"cmd":"head skills/wa/SKILL.md skills/workplan/SKILL.md"}'])
        self.assertEqual(self.loaded(out), {'wa', 'workplan'})

    def test_the_load_carries_a_timestamp_so_recency_works(self):
        out = self.scan(['{"cmd":"cat skills/wa/SKILL.md"}'])
        attempt = out['sessions'][0]['skill_attempts'][0]
        self.assertTrue(attempt.get('at'))


class GapsThatWorked(unittest.TestCase):
    """A skill that loaded successfully is not a defect just because the inventory
    could not find its file. Over a 90-day window that produced 37 "worth checking"
    findings on a real machine, every one a skill that ran fine: mostly plugins
    installed and removed inside a week. Churn reported as breakage."""

    def scan(self, gap, failed=()):
        sessions = [{'skill_attempts': [{'name': n} for n in gap],
                     'confirmed_skill_loads': [{'name': n} for n in gap if n not in failed],
                     'failed_skill_loads': [{'name': n} for n in failed],
                     'turns': [1]}]
        return analyze({'schema_version': 'brain-surgery-inspection/0.3',
                        'skills': [{'name': 'present', 'aliases': ['present'],
                                    'path': '/x/present/SKILL.md'}],
                        'sessions': sessions, 'inventory_gap': list(gap)})

    def test_gaps_that_loaded_cleanly_collapse_to_one_coverage_note(self):
        result = self.scan(['a', 'b', 'c'])
        gaps = [f for f in result['findings'] if f['code'] == 'inventory_gap']
        self.assertEqual(len(gaps), 1)
        self.assertIsNone(gaps[0]['skill'])
        self.assertEqual(gaps[0]['confidence'], 'observation')
        self.assertEqual(gaps[0]['evidence']['names'], ['a', 'b', 'c'])

    def test_a_gap_whose_loads_errored_stays_a_real_finding(self):
        """That one is a real problem: the agent reached for it and got nothing
        back. It keeps a per-skill finding rather than vanishing into the coverage
        note, and root-cause deduplication then reports the failure and the gap as
        one thing, since they are one thing."""
        result = self.scan(['a', 'broken'], failed=['broken'])
        hits = [f for f in result['findings'] if f.get('skill') == 'broken']
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]['code'], 'load_failed')
        self.assertEqual(hits[0]['confidence'], 'suspected')
        self.assertIn('inventory_gap', hits[0].get('also_reported_as', []))
        # And the clean gap is still summarised separately.
        note = [f for f in result['findings']
                if f['code'] == 'inventory_gap' and f['skill'] is None]
        self.assertEqual(note[0]['evidence']['names'], ['a'])

    def test_no_gaps_means_no_coverage_note(self):
        result = self.scan([])
        self.assertEqual([f for f in result['findings'] if f['code'] == 'inventory_gap'], [])


class HostileInput(unittest.TestCase):
    """What a stranger's machine does to the scan. A crash is worse than
    imprecision, and a silent skip is worse than both, because the user then
    believes a smaller number than the one that was measured."""

    def scan(self, build):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills = root / 'skills'
            skills.mkdir()
            logs = root / 'logs'
            logs.mkdir()
            build(skills, logs)
            try:
                return inspect(root / 'p', 'claude', [skills], [logs],
                               days=365, explicit=True, scope='user')
            finally:
                for p in skills.rglob('*'):
                    if p.is_dir():
                        p.chmod(0o755)

    def declare(self, path: Path, body: str):
        path.mkdir(parents=True, exist_ok=True)
        (path / 'SKILL.md').write_text(body)

    def test_an_unreadable_directory_is_reported_as_a_bound(self):
        """It was skipped in silence, so the user saw a smaller inventory than the
        machine has with nothing on the page saying so."""
        def build(skills, logs):
            self.declare(skills / 'fine', '---\nname: fine\ndescription: d\n---\n')
            self.declare(skills / 'locked', '---\nname: locked\ndescription: d\n---\n')
            (skills / 'locked').chmod(0)
        out = self.scan(build)
        self.assertTrue(any('Could not read' in w for w in out['warnings']), out['warnings'])

    def test_a_missing_name_is_not_a_fault(self):
        """The host addresses a skill by its directory name, so a `name` field is
        optional. `~/.claude/skills/chrome-cdp-skill/SKILL.md` has no frontmatter
        at all and was invoked eight times through the Skill tool, which is how the
        first version of this check was caught claiming the opposite."""
        def build(skills, logs):
            self.declare(skills / 'noname', '---\ndescription: d\n---\n')
        out = self.scan(build)
        self.assertIsNone(out['skills'][0]['malformed'])

    def test_a_missing_description_is_flagged(self):
        """The description is what the agent reads when deciding whether a skill
        fits the task, so without one the skill can only be called by name. That is
        how a good skill sits installed and never gets reached."""
        def build(skills, logs):
            self.declare(skills / 'nodesc', '---\nname: nodesc\n---\n')
            self.declare(skills / 'bare', 'no frontmatter at all')
            self.declare(skills / 'ok', '---\nname: ok\ndescription: d\n---\n')
        out = self.scan(build)
        by = {s['name']: s for s in out['skills']}
        self.assertEqual(by['nodesc']['malformed'], ['no description'])
        self.assertEqual(by['bare']['malformed'], ['no description'])
        self.assertIsNone(by['ok']['malformed'])

    def test_corrupt_and_oversized_transcripts_do_not_stop_the_scan(self):
        def build(skills, logs):
            self.declare(skills / 'ok', '---\nname: ok\ndescription: d\n---\n')
            (logs / 'truncated.jsonl').write_text('{"type":"user","message":')
            (logs / 'binary.jsonl').write_bytes(b'\x00\xff\xfe\x00\n')
            (logs / 'empty.jsonl').write_text('')
            (logs / 'huge.jsonl').write_text(
                '{"type":"user","message":{"content":"' + 'x' * 900000 + '"}}\n')
        out = self.scan(build)
        self.assertEqual(len(out['skills']), 1)

    def test_a_symlink_cycle_in_a_skill_root_terminates(self):
        def build(skills, logs):
            self.declare(skills / 'ok', '---\nname: ok\ndescription: d\n---\n')
            (skills / 'loop').symlink_to(skills)
        out = self.scan(build)
        self.assertEqual({s['name'] for s in out['skills']}, {'ok'})


class NoDescriptionFinding(unittest.TestCase):
    def test_it_claims_untriggerable_not_unloadable(self):
        """The claim has to match the evidence. A skill with no description still
        loads when named; what it cannot do is get chosen."""
        result = analyze({'schema_version': 'brain-surgery-inspection/0.3',
                          'skills': [{'name': 'quiet', 'aliases': ['quiet'],
                                      'path': '/x/quiet/SKILL.md',
                                      'malformed': ['no description']}],
                          'sessions': [{'turns': [1]}], 'inventory_gap': []})
        hit = [f for f in result['findings'] if f['code'] == 'no_description'][0]
        self.assertEqual(hit['confidence'], 'confirmed')
        self.assertIn('nothing can trigger it', hit['title'])
        self.assertNotIn('will not load', hit['detail'])
        self.assertIn('never loaded', hit['detail'])
        self.assertIn('/x/quiet/SKILL.md', hit['fix'])
        self.assertIn('description:', hit['fix'])

    def test_it_distinguishes_never_loaded_from_loaded_only_when_named(self):
        """Both were on one real machine and they are different problems.
        chrome-cdp-skill had loaded 8 times, every one because something named it;
        phase-b-e2e-skill had never run. One line for both tells neither reader
        what to do."""
        base = {'schema_version': 'brain-surgery-inspection/0.3',
                'skills': [{'name': 'named', 'aliases': ['named'],
                            'path': '/x/named/SKILL.md', 'malformed': ['no description']}],
                'inventory_gap': []}
        used = analyze(dict(base, sessions=[{
            'skill_attempts': [{'name': 'named'}] * 3,
            'confirmed_skill_loads': [{'name': 'named'}] * 3, 'turns': [1]}]))
        hit = [f for f in used['findings'] if f['code'] == 'no_description'][0]
        self.assertIn('loaded 3 times', hit['detail'])
        self.assertEqual(hit['evidence']['loads'], 3)

        never = analyze(dict(base, sessions=[{'turns': [1]}]))
        hit = [f for f in never['findings'] if f['code'] == 'no_description'][0]
        self.assertIn('never loaded', hit['detail'])
        self.assertEqual(hit['evidence']['loads'], 0)


class HostDetection(unittest.TestCase):
    """`--host auto` on a machine running both agents. The first version looked for
    one `session_meta` row in the first 20 lines and assumed Claude otherwise, so a
    Codex rollout without that marker near the top was parsed with Claude rules and
    every skill load in it was lost in silence."""

    def test_a_codex_rollout_without_session_meta_is_still_codex(self):
        rows = [{'type': 'response_item', 'payload': {'type': 'custom_tool_call'}}] * 5
        self.assertEqual(detect_host(rows), 'codex')

    def test_a_claude_transcript_is_claude(self):
        self.assertEqual(detect_host([{'type': 'assistant', 'message': {'content': []}}] * 5),
                         'claude')

    def test_a_majority_decides_rather_than_a_single_marker(self):
        rows = [{'type': 'assistant', 'message': {}}] * 9 + [{'type': 'session_meta'}]
        self.assertEqual(detect_host(rows), 'claude')

    def test_an_unrecognisable_file_does_not_crash(self):
        for rows in ([], [1, 'x', None], [{'nothing': 'useful'}]):
            self.assertIn(detect_host(rows), ('claude', 'codex'))

    def test_auto_reads_a_codex_load_that_claude_rules_would_miss(self):
        """End to end: the same mixed log directory under --host auto must surface
        the Codex skill read, not just the Claude one."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills, logs = root / 'skills', root / 'logs'
            (skills / 'ok').mkdir(parents=True)
            (skills / 'ok' / 'SKILL.md').write_text('---\nname: ok\ndescription: d\n---\n')
            (skills / 'cx').mkdir(parents=True)
            (skills / 'cx' / 'SKILL.md').write_text('---\nname: cx\ndescription: d\n---\n')
            logs.mkdir()
            (logs / 'claude.jsonl').write_text('\n'.join(json.dumps(r) for r in [
                {'type': 'assistant', 'cwd': str(root), 'timestamp': '2026-09-18T10:00:00Z',
                 'message': {'role': 'assistant', 'content': [
                     {'type': 'tool_use', 'id': 'u1', 'name': 'Skill', 'input': {'skill': 'ok'}}]}},
                {'type': 'user', 'cwd': str(root), 'timestamp': '2026-09-18T10:00:00Z',
                 'message': {'role': 'user', 'content': [
                     {'type': 'tool_result', 'tool_use_id': 'u1', 'content': 'loaded'}]}}]))
            (logs / 'codex.jsonl').write_text(json.dumps(
                {'type': 'response_item', 'timestamp': '2026-09-18T11:00:00Z',
                 'payload': {'type': 'custom_tool_call', 'name': 'exec',
                             'input': '{"cmd":"cat skills/cx/SKILL.md"}'}}))
            out = inspect(root, 'auto', [skills], [logs], days=365,
                          explicit=True, scope='user')
        loaded = {a['name'] for s in out['sessions'] for a in s['confirmed_skill_loads']}
        self.assertEqual(loaded, {'ok', 'cx'})


class CrossHostRoots(unittest.TestCase):
    """Once the inventory covered both agents' roots, mirroring a skill into each
    produced 57 "stored twice" observations and 7 false collisions. That mirroring
    is the documented deployment pattern: one canonical store linked into every
    harness. Two copies can only shadow each other if one agent sees both."""

    def entry(self, name, root, path, digest='same'):
        return {'name': name, 'aliases': [name], 'path': path,
                'found_under': root, 'skill_md_sha256': digest}

    def scan(self, *entries):
        return analyze({'schema_version': 'brain-surgery-inspection/0.3',
                        'skills': list(entries), 'sessions': [{'turns': [1]}],
                        'inventory_gap': []})

    def hits(self, result, name):
        return [f for f in result['findings'] if f.get('skill') == name]

    def test_the_same_skill_in_a_claude_root_and_a_codex_root_is_not_a_collision(self):
        r = self.scan(self.entry('wa', '/h/.claude/skills', '/h/.claude/skills/wa/SKILL.md', 'a'),
                     self.entry('wa', '/h/.codex/skills', '/h/.codex/skills/wa/SKILL.md', 'b'))
        self.assertEqual(self.hits(r, 'wa'), [])

    def test_two_copies_inside_one_host_are_still_compared(self):
        r = self.scan(self.entry('wa', '/h/.claude/skills', '/h/.claude/skills/wa/SKILL.md', 'a'),
                     self.entry('wa', '/h/.agents/skills', '/h/.agents/skills/wa/SKILL.md', 'b'))
        self.assertEqual([f['code'] for f in self.hits(r, 'wa')], ['shadowed'])

    def test_the_canonical_store_counts_as_whichever_host_links_to_it(self):
        """`~/.agents/skills` is the shared store, not a third agent. Treating it as
        its own host would silence a real drift between it and a harness root."""
        r = self.scan(self.entry('wa', '/h/.agents/skills', '/h/.agents/skills/wa/SKILL.md', 'a'),
                     self.entry('wa', '/h/.codex/skills', '/h/.codex/skills/wa/SKILL.md', 'b'))
        self.assertEqual([f['code'] for f in self.hits(r, 'wa')], ['shadowed'])

    def test_scoping_uses_the_root_not_the_resolved_path(self):
        """Two harness roots symlinking into project directories resolve to paths
        carrying no harness marker at all, so scoping on the resolved path read two
        links to one place as a collision. Found on a real machine, where .agents
        and .codex pointed at two different checkouts of the same project."""
        r = self.scan(self.entry('vid', '/h/.claude/skills', '/h/Projects/a/skills/vid/SKILL.md', 'a'),
                     self.entry('vid', '/h/.codex/skills', '/h/Projects/b/skills/vid/SKILL.md', 'b'))
        self.assertEqual(self.hits(r, 'vid'), [])


class RootsFollowTheHostsRead(unittest.TestCase):
    """Under `--host auto` the log side reads both Claude and Codex transcripts,
    and the skill side built Claude roots only. Every Codex skill that ran came
    back as "loaded but not found on disk": 37 of them on a real machine. Not a
    fault in the setup, the scan looking in one place and listening in two."""

    def roots(self, host):
        return [str(p) for p in default_skill_roots(Path('/proj'), Path('/home/u'), host)]

    def test_auto_covers_both_hosts(self):
        r = self.roots('auto')
        self.assertTrue(any('/.claude/skills' in p for p in r), r)
        self.assertTrue(any('/.codex/skills' in p for p in r), r)

    def test_a_named_host_stays_narrow_at_the_user_level(self):
        """Pooling the other host's machine-wide store into a single-host scan
        counts every shared skill twice, which is the bug the narrowing originally
        fixed. Project-local roots are a different matter: a `.claude/skills`
        directory inside a project is there because someone put it there, and it
        is included for every host on purpose."""
        home = '/home/u'
        claude = [p for p in self.roots('claude') if p.startswith(home)]
        self.assertFalse(any('/.codex/' in p for p in claude), claude)
        codex = [p for p in self.roots('codex') if p.startswith(home)]
        self.assertFalse(any('/.claude/' in p for p in codex), codex)

    def test_plugin_caches_are_looked_for_under_every_host_read(self):
        """`spreadsheets` and `firecrawl` live in ~/.codex/plugins/cache and were
        reported as missing from disk because only the Claude cache was globbed."""
        import inspect_setup
        seen = []
        original = inspect_setup.plugin_cache_roots
        inspect_setup.plugin_cache_roots = lambda cache: seen.append(str(cache)) or []
        try:
            default_skill_roots(Path('/proj'), Path('/home/u'), 'auto')
        finally:
            inspect_setup.plugin_cache_roots = original
        self.assertTrue(any('.claude/plugins/cache' in c for c in seen), seen)
        self.assertTrue(any('.codex/plugins/cache' in c for c in seen), seen)


class SymlinkedSkillFile(unittest.TestCase):
    """A SKILL.md that is itself a symlink into a shared skill. On a real server,
    `_gstack-command/SKILL.md -> gstack/SKILL.md` and many like it, which is a
    working layout. The scan aborted outright on the first one and never read the
    other 300 skills on that machine."""

    def test_a_symlinked_skill_file_is_inventoried_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'real').mkdir()
            (root / 'real' / 'SKILL.md').write_text(
                '---\nname: real\ndescription: d\n---\n\nbody\n')
            (root / 'alias').mkdir()
            (root / 'alias' / 'SKILL.md').symlink_to(root / 'real' / 'SKILL.md')
            inv = inventory([root])
        names = {s['name'] for s in inv['skills']}
        self.assertEqual(names, {'real', 'alias'})

    def test_the_digest_is_of_the_bytes_actually_read(self):
        """Digesting the decoded text would be wrong: errors='replace' rewrites
        bytes, so two different files could collapse to one digest and be reported
        as identical copies."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, body in (('a', b'\xff\xfe one'), ('b', b'\xff\xfe two')):
                (root / name).mkdir()
                (root / name / 'SKILL.md').write_bytes(
                    b'---\nname: ' + name.encode() + b'\ndescription: d\n---\n' + body)
            inv = inventory([root])
        digests = {s['skill_md_sha256'] for s in inv['skills']}
        self.assertEqual(len(digests), 2)

    def test_an_unreadable_skill_file_is_skipped_with_a_warning_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'broken').mkdir()
            (root / 'broken' / 'SKILL.md').symlink_to(root / 'nowhere' / 'SKILL.md')
            (root / 'fine').mkdir()
            (root / 'fine' / 'SKILL.md').write_text('---\nname: fine\ndescription: d\n---\n')
            inv = inventory([root])
        self.assertEqual({s['name'] for s in inv['skills']}, {'fine'})


class SkillSubtreesAreNotMoreSkills(unittest.TestCase):
    """Found on a server, invisible on a laptop. Both cases produced dozens of
    confirmed collisions that were entirely the scan's own doing."""

    def declare(self, path: Path, name: str):
        path.mkdir(parents=True, exist_ok=True)
        (path / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: d\n---\n')

    def test_a_skill_shipping_copies_for_other_harnesses_counts_once(self):
        """`gstack/.agents/skills/gstack/SKILL.md`, plus .cursor, .factory,
        .gbrain, .hermes, .kiro. Nine copies of every gstack skill, reported as a
        nine-way collision. Only the top-level directory is addressable."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.declare(root / 'gstack', 'gstack')
            for harness in ('.agents', '.cursor', '.factory', '.gbrain'):
                self.declare(root / 'gstack' / harness / 'skills' / 'gstack', 'gstack')
            inv = inventory([root])
        self.assertEqual([s['name'] for s in inv['skills']], ['gstack'])

    def test_backups_inside_a_skill_root_are_not_skills(self):
        """`.codex/skills/.floom/backups/<timestamp>/SKILL.md`. Every backup was
        inventoried as a skill named after its timestamp and then reported as a
        39-way name collision."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.declare(root / 'real', 'real')
            for stamp in ('2026-05-23T23-06-47', '2026-05-23T23-07-27'):
                self.declare(root / '.floom' / 'backups' / stamp, 'real')
            inv = inventory([root])
        self.assertEqual([s['name'] for s in inv['skills']], ['real'])

    def test_a_skill_directly_in_the_root_is_still_found(self):
        """The descent guard must not swallow the ordinary case: a root that holds
        SKILL.md files one level down."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for n in ('a', 'b', 'c'):
                self.declare(root / n, n)
            inv = inventory([root])
        self.assertEqual(sorted(s['name'] for s in inv['skills']), ['a', 'b', 'c'])

    def test_a_skill_md_at_the_root_itself_is_still_found(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'SKILL.md').write_text('---\nname: top\ndescription: d\n---\n')
            self.declare(root / 'nested', 'nested')
            inv = inventory([root])
        self.assertEqual(sorted(s['name'] for s in inv['skills']),
                         sorted([Path(d).name, 'nested']))
