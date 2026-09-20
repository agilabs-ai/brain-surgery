"""Tests for apply_surgery: the one script that writes into the user's CLAUDE.md.

The property under test is the one a first user actually probes, and it is not
"does it help". It is **does it leave a healthy setup alone**. A tool that edits
a config file earns trust by declining to, so most of what follows asserts that
nothing was written and that the target is byte-identical afterwards.

Every refusal test has a positive counterpart built from the same fixture with
one field changed. A guard that cannot fire is not a guard, and a script that
refuses everything would pass a suite of refusal tests alone while being
useless. `test_dormant_routable_skill_is_written` is what stops that: it is the
control, and if it ever fails the negative tests below mean nothing.

The write-path tests go through the CLI rather than calling plan() directly.
What matters is the bytes on disk after a real invocation, and the exit code a
user's shell sees, not what the planner returned on the way there.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from apply_surgery import BEGIN, END, SCHEMA, candidates, derive_trigger, plan

SCRIPT = ROOT / 'scripts' / 'apply_surgery.py'

# A CLAUDE.md with content of its own. Surgery must never disturb what is
# already here, so it is asserted intact in every test that writes.
EXISTING = b"""# House rules

Reply in English. Never use em dashes.

## Deploy

Production runs on the primary host only.
"""


def skill(root: Path, name: str, description: str) -> Path:
    """Write a SKILL.md the inventory walker will pick up."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / 'SKILL.md').write_text(
        "---\nname: %s\ndescription: %s\n---\n\n# %s\n\nBody.\n" % (name, description, name),
        encoding='utf-8')
    return d


def scan(dormant_names, *, measured=True, installed=None, shadowed=(), failed=(), outside=()):
    """A findings record shaped like analyze_scan.py's output.

    `dormant_names` is the list analyze_scan puts in evidence.names. A healthy
    machine still emits the dormant finding, with that list empty and a title
    reading "0 of N" — the finding is the measurement, not the alarm. Passing []
    here is therefore the healthy case, not a missing finding.
    """
    installed = installed if installed is not None else max(len(dormant_names), 1)
    findings = []
    for name in failed:
        findings.append({'code': 'load_failed', 'skill': name, 'title': 'failed to load',
                         'detail': '', 'evidence': {'attempts': 2, 'confirmed_loads': 0}})
    for name in shadowed:
        findings.append({'code': 'shadowed', 'skill': name, 'title': 'declared twice',
                         'detail': '', 'evidence': {'paths': ['/a/%s' % name, '/b/%s' % name]}})
    for name in outside:
        findings.append({'code': 'inventory_gap', 'skill': name, 'title': 'loaded from outside',
                         'detail': '', 'evidence': {'confirmed_loads': 3}})
    if measured:
        findings.append({
            'code': 'dormant', 'skill': None,
            'title': '%d of %d installed skills were never used' % (len(dormant_names), installed),
            'detail': 'Installed and available; never loaded in the window.',
            'evidence': {'installed': installed, 'reached': installed - len(dormant_names),
                         'dormant': len(dormant_names), 'names': list(dormant_names)}})
    else:
        findings.append({'code': 'no_evidence', 'skill': None,
                         'title': '%d skills found, but no sessions could be read' % installed,
                         'detail': 'Nothing here is a measurement.',
                         'evidence': {'installed': installed, 'sessions_analyzed': 0}})
    return {
        'schema_version': SCHEMA, 'created_at': '2026-09-18T08:00:00Z',
        'project': '/Users/someone/project', 'host': 'claude',
        'evaluation_performed': False, 'change_status': 'not_applied',
        'totals': {'measured': measured, 'installed': installed,
                   'reached': installed - len(dormant_names), 'dormant': len(dormant_names),
                   'loaded_outside_inventory': len(outside),
                   'dormant_percent': round(100 * len(dormant_names) / installed) if measured
                   else None,
                   'load_attempts': 40, 'confirmed_loads': 38, 'failed_loads': len(failed)},
        'most_used': [], 'findings': findings,
        'coverage': {'sessions_analyzed': 120, 'turns_analyzed': 9000, 'window_days': 30},
        'scan_limits': {'days': 30, 'max_sessions': 500},
        'privacy': 'Counts and skill names only.',
    }


@pytest.fixture
def bed(tmp_path):
    """A machine: one skill root on disk, a CLAUDE.md, and somewhere for input."""
    roots = tmp_path / 'skills'
    roots.mkdir()
    # Routable: a 'Use when' condition in task shape, which is the only kind
    # derive_trigger will lift without guessing.
    skill(roots, 'pdf-extract', 'Use when extracting tables from a PDF.')
    skill(roots, 'csv-merge', 'Use when merging CSV files on a shared key.')
    # Author voice: refused by name, never rewritten.
    skill(roots, 'dm-voice', 'Use when writing any in-session reply to Federico.')
    target = tmp_path / 'CLAUDE.md'
    target.write_bytes(EXISTING)
    return {'root': tmp_path, 'roots': roots, 'target': target}


def run(bed, findings, *args, expect=None):
    path = bed['root'] / 'findings.json'
    path.write_text(json.dumps(findings), encoding='utf-8')
    cmd = [sys.executable, str(SCRIPT), '--input', str(path), '--target', str(bed['target']),
           '--skill-root', str(bed['roots']), '--project', str(bed['root']),
           # The synthetic fixture calls its machine owner Federico. Declare that
           # identity instead of accidentally inheriting the developer account's
           # login name; clean CI runners are intentionally named something else.
           '--owner-name', 'Federico'] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if expect is not None:
        assert p.returncode == expect, "exit %d, wanted %d\n%s\n%s" % (
            p.returncode, expect, p.stdout, p.stderr)
    return p


# ---------------------------------------------------------------------------
# Unnecessary Surgery Rate: the healthy machine
# ---------------------------------------------------------------------------

def test_healthy_setup_is_left_alone(bed):
    """Every installed skill was reached. Nothing to route, so nothing is written.

    This is the headline property. The scan still carries a dormant finding
    here, reading "0 of N", so the script cannot shortcut on the finding being
    absent: it has to look at the names list and find it empty.
    """
    p = run(bed, scan([], installed=12), '--confirm', expect=1)
    assert bed['target'].read_bytes() == EXISTING
    assert 'Nothing to write' in p.stdout


def test_healthy_setup_leaves_no_backup(bed):
    """A refusal is not a change, so it must not litter the directory either.

    A stray .bak beside a CLAUDE.md reads as "something edited this file" to
    anyone who finds it later, which is exactly the wrong thing to tell someone
    whose setup was never touched.
    """
    run(bed, scan([], installed=12), '--confirm', expect=1)
    assert [q.name for q in bed['root'].iterdir() if '.bak' in q.name] == []


def test_every_dormant_skill_is_blocked_so_nothing_is_written(bed):
    """Dormant, but each for a reason routing cannot fix.

    Shadowed resolves by load order, a failed skill is broken, and one loaded
    from outside the inventory has no description to read. The count is alarming
    and the correct action is still to write nothing.
    """
    f = scan(['pdf-extract', 'csv-merge', 'ghost'], installed=9,
             shadowed=['pdf-extract'], failed=['csv-merge'], outside=['ghost'])
    run(bed, f, '--confirm', expect=1)
    assert bed['target'].read_bytes() == EXISTING


def test_unmeasured_scan_is_refused_even_with_dormant_names(bed):
    """measured=false means no transcript was read, so dormancy is an artefact.

    The fixture deliberately still lists dormant names, because the dangerous
    version of this bug is the one where the names look actionable and only the
    flag says they are not.
    """
    f = scan(['pdf-extract', 'csv-merge'], installed=2, measured=False)
    f['totals']['measured'] = False
    f['totals']['dormant'] = 2
    f['findings'].append({'code': 'dormant', 'skill': None, 'title': 'planted',
                          'detail': '', 'evidence': {'names': ['pdf-extract', 'csv-merge']}})
    p = run(bed, f, '--confirm', expect=1)
    assert bed['target'].read_bytes() == EXISTING
    assert 'measured no usage' in (p.stdout + p.stderr)


def test_wrong_schema_is_refused(bed):
    """A comparison record is not a scan. Neither is a hand-written file."""
    f = scan(['pdf-extract'])
    f['schema_version'] = 'brain-surgery/0.4'
    p = run(bed, f, '--confirm', expect=1)
    assert bed['target'].read_bytes() == EXISTING
    assert 'brain-surgery-scan/0.1' in (p.stdout + p.stderr)


def test_dry_run_is_the_default(bed):
    """Without --confirm a routable finding still writes nothing."""
    p = run(bed, scan(['pdf-extract'], installed=4), expect=0)
    assert bed['target'].read_bytes() == EXISTING
    assert 'Dry run' in p.stdout


def test_dry_run_beats_confirm(bed):
    """Both flags together go the way that changes nothing."""
    run(bed, scan(['pdf-extract'], installed=4), '--confirm', '--dry-run', expect=0)
    assert bed['target'].read_bytes() == EXISTING


# ---------------------------------------------------------------------------
# The control: surgery does happen when it is warranted
# ---------------------------------------------------------------------------

def test_dormant_routable_skill_is_written(bed):
    """The positive control. Without this, every refusal test above is vacuous."""
    run(bed, scan(['pdf-extract', 'csv-merge'], installed=9), '--confirm', expect=0)
    after = bed['target'].read_bytes()
    assert BEGIN in after and END in after
    assert b'pdf-extract' in after and b'csv-merge' in after
    # Prose the user wrote is untouched, and the block is appended rather than
    # spliced into the middle of it.
    assert after.startswith(EXISTING)


def test_author_voice_skill_is_refused_not_rewritten(bed):
    """dm-voice is dormant and routable-looking, and gets no row.

    There is no mechanical way to turn "any in-session reply to Federico" into a
    task condition, and a guessed trigger that looks right is worse than none.
    """
    p = run(bed, scan(['dm-voice'], installed=9), '--confirm', expect=1)
    assert bed['target'].read_bytes() == EXISTING
    assert 'author voice' in p.stdout


def test_author_voice_does_not_suppress_its_neighbours(bed):
    """One refused skill must not take the routable ones down with it."""
    run(bed, scan(['dm-voice', 'pdf-extract'], installed=9), '--confirm', expect=0)
    after = bed['target'].read_bytes()
    assert b'pdf-extract' in after
    assert b'dm-voice' not in after.split(BEGIN)[1]


# ---------------------------------------------------------------------------
# Re-running on a machine that already had surgery
# ---------------------------------------------------------------------------

def test_reapplying_the_same_scan_is_idempotent(bed):
    """Same scan twice, same bytes.

    A user who re-runs the scan weekly gets this path far more often than the
    first-write path, and a block that churns on every run makes the diff
    worthless and the tool feel unsafe.
    """
    f = scan(['pdf-extract', 'csv-merge'], installed=9)
    run(bed, f, '--confirm', expect=0)
    first = bed['target'].read_bytes()
    run(bed, f, '--confirm', expect=0)
    second = bed['target'].read_bytes()
    # The stamp carries a timestamp, so compare everything outside the block
    # plus the row content, which is what a reader would notice changing.
    assert first.split(BEGIN)[0] == second.split(BEGIN)[0]
    assert b'pdf-extract' in second and b'csv-merge' in second


def test_healthy_rescan_does_not_remove_an_existing_block(bed):
    """A machine that got healthy is not a machine to silently edit.

    If every routed skill is now reached, the right move is still to write
    nothing and say so. Ripping the block back out would be a second
    unrequested edit, and the user can remove it themselves.
    """
    run(bed, scan(['pdf-extract'], installed=9), '--confirm', expect=0)
    with_block = bed['target'].read_bytes()
    run(bed, scan([], installed=9), '--confirm', expect=1)
    assert bed['target'].read_bytes() == with_block


def test_rollback_restores_byte_identical(bed):
    run(bed, scan(['pdf-extract'], installed=9), '--confirm', expect=0)
    assert bed['target'].read_bytes() != EXISTING
    run(bed, scan(['pdf-extract'], installed=9), '--rollback', '--confirm', expect=0)
    assert bed['target'].read_bytes() == EXISTING


# ---------------------------------------------------------------------------
# Targets the script must not write to
# ---------------------------------------------------------------------------

def test_symlink_target_is_refused(bed, tmp_path):
    """Following a symlink writes into a file the user did not name."""
    real = tmp_path / 'real-CLAUDE.md'
    real.write_bytes(EXISTING)
    link = tmp_path / 'link-CLAUDE.md'
    link.symlink_to(real)
    path = bed['root'] / 'findings.json'
    path.write_text(json.dumps(scan(['pdf-extract'], installed=9)), encoding='utf-8')
    p = subprocess.run(
        [sys.executable, str(SCRIPT), '--input', str(path), '--target', str(link),
         '--skill-root', str(bed['roots']), '--project', str(bed['root']), '--confirm'],
        capture_output=True, text=True)
    assert p.returncode != 0
    assert real.read_bytes() == EXISTING


def test_unpaired_marker_is_refused(bed):
    """A begin with no end means the file was hand-edited. Splicing would eat it."""
    bed['target'].write_bytes(EXISTING + b"\n" + BEGIN + b"\nhand edited\n")
    before = bed['target'].read_bytes()
    p = run(bed, scan(['pdf-extract'], installed=9), '--confirm')
    assert p.returncode != 0
    assert bed['target'].read_bytes() == before


def test_two_blocks_are_refused(bed):
    """Which one to replace is not knowable, so neither is touched."""
    block = BEGIN + b"\nrows\n" + END
    bed['target'].write_bytes(EXISTING + b"\n" + block + b"\n\n" + block + b"\n")
    before = bed['target'].read_bytes()
    p = run(bed, scan(['pdf-extract'], installed=9), '--confirm')
    assert p.returncode != 0
    assert bed['target'].read_bytes() == before


# ---------------------------------------------------------------------------
# Planner-level, where the CLI would hide which rule fired
# ---------------------------------------------------------------------------

def test_candidates_subtracts_blocked_names_from_dormant():
    f = scan(['a', 'b', 'c'], installed=9, shadowed=['a'], failed=['b'])
    names, shadowed, failed, outside = candidates(f)
    assert names == ['c']
    assert set(shadowed) == {'a'} and failed == ['b']


def test_max_rows_caps_and_reports_the_cut(bed, tmp_path):
    names = []
    for i in range(8):
        n = 'tool-%d' % i
        skill(bed['roots'], n, 'Use when processing batch %d of records.' % i)
        names.append(n)
    p = plan(scan(names, installed=20), [bed['roots']], 3, [], set())
    assert len(p['rows']) == 3
    assert p['eligible'] == 8 and p['dropped'] == 5


def test_only_overrides_dormancy_but_not_the_block_list(bed):
    """--only lets a user route a reached skill; it does not unblock a broken one."""
    f = scan([], installed=9, shadowed=['csv-merge'])
    p = plan(f, [bed['roots']], 12, ['pdf-extract', 'csv-merge'], set())
    assert [r['skill'] for r in p['rows']] == ['pdf-extract']


@pytest.mark.parametrize('desc,routable', [
    ('Use when extracting tables from a PDF.', True),
    ('Use when the user wants to merge two CSV files.', True),
    ('Use when writing any in-session reply to Federico.', False),
    ('Use when I need to check the deploy.', False),
    ('This skill renders PDF reports.', False),
    ('', False),
])
def test_derive_trigger_direction(desc, routable):
    """Both directions on the same function, since a guard that always refuses
    would otherwise look identical to a correct one."""
    trigger, _tier, reason = derive_trigger(desc, {'federico'})
    assert bool(trigger) is routable, reason or trigger
    if routable:
        assert trigger.startswith('the task is ')
