#!/usr/bin/env python3
"""Recompute `skill_loaded` on finished records from their saved transcripts.

`skill_loaded` is a read of the transcript, not a measurement of the run, so it
can be corrected after the fact without re-running anything. Pass/fail is never
touched: this only rewrites the field that says whether the agent reached the
skill, plus a note recording that it was recomputed rather than observed live.

Usage:  python3 eval/recompute_skill_load.py <grid-out-dir> [--apply]
Without --apply it reports what would change and writes nothing.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_grid import detect_skill_load  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    apply = '--apply' in sys.argv
    if not args:
        print(__doc__)
        return 2
    out = Path(args[0]).expanduser()

    changed, same, missing = [], 0, 0
    tally: Counter = Counter()
    for rec_path in sorted(out.rglob('record.json')):
        rec = json.loads(rec_path.read_text())
        tr = rec_path.parent / 'stdout.jsonl'
        if not tr.exists():
            missing += 1
            continue
        fresh = detect_skill_load(tr.read_text(), rec['skill'])
        tally[(rec['arm'], fresh)] += 1
        if fresh != rec.get('skill_loaded'):
            changed.append((rec['arm'], rec['task'], rec.get('skill_loaded'), fresh))
            if apply:
                rec['skill_loaded'] = fresh
                rec['skill_loaded_recomputed'] = True
                rec_path.write_text(json.dumps(rec, indent=2))
        else:
            same += 1

    print(f'{len(changed)} changed, {same} unchanged, {missing} without a transcript')
    print('\nrecomputed skill_loaded by arm:')
    for arm in sorted({a for a, _ in tally}):
        row = {v: tally[(arm, v)] for v in (True, False, None) if tally[(arm, v)]}
        print(f'  {arm}: {row}')
    if changed[:12]:
        print('\nfirst changes:')
        for arm, task, old, new in changed[:12]:
            print(f'  {arm} {task:28s} {old} -> {new}')
    if not apply and changed:
        print('\nnothing written; re-run with --apply')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
