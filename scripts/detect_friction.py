#!/usr/bin/env python3
"""Find sessions that went badly, without a judge.

The product's useful finding is not "you have 163 dormant skills". It is "these
sessions went badly and these installed skills never fired in them". Getting there
normally needs a jurisdiction call, deciding which skill *should* have applied to a
task, which is a semantic matching problem and a judgment per task.

This inverts it, the way Warp's skill-doctor does: do not ask whether a skill was
eligible, ask which sessions went badly and which skills were absent from them. That
removes the matching problem entirely.

Warp gets "went badly" from model-judge subagents. This tries to get it from the
transcript alone, deterministically, because a judge costs money on every scan and
cannot be pinned by a test.

## The signals, and why each one is weak on its own

- `correction`  a short user turn that negates or redirects what just happened. The
                strongest single signal, because the user is the ground truth on
                whether the work was right, and they said so in their own words.
- `repetition`  the same request restated. Distinguished from a follow-up by
                similarity of the opening words, not by length.
- `tool_error`  an explicit tool error in the trace. Cheap to count and genuinely
                ambiguous: a failed grep is not a failed session.
- `bloat`       many turns for a small opening ask. A proxy for thrash, and the
                signal most likely to misfire on genuinely large tasks.

None of these is reliable alone. The question this script exists to answer is whether
they are reliable *together*, judged against the only ground truth available: the
user reading a sample and saying whether the ranking is right.

Read-only. No model calls, no network, no writes outside --out.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# A correction is short, and it negates or redirects. Length matters: "no" after a
# long assistant turn is a correction, while a long message beginning "no" is usually
# a new instruction that happens to open with a qualifier.
CORRECTION = re.compile(
    r"^\s*(no+\b|nope\b|nein\b|wrong\b|that'?s (not|wrong)|not (like )?(that|what)|"
    r"i (said|asked|meant)\b|revert\b|undo\b|stop\b|why (did|are) you\b|"
    r"you (didn'?t|did not|forgot|ignored|missed)\b|again\b|still (not|wrong|broken)\b)",
    re.I)
#: Frustration markers that are not necessarily corrections but rarely appear in a
#: session that went well.
FRICTION_WORDS = re.compile(r"\b(wtf|for fuck'?s sake|come on|seriously\?|ffs)\b", re.I)

MAX_CORRECTION_CHARS = 180


def turns(path: Path):
    """Yield (role, text) for real conversation turns only.

    Tool results arrive as `user` rows and would otherwise be counted as the user
    speaking, which would make every tool-heavy session look like an argument.
    Compaction summaries are excluded for the same reason: they are machine text
    quoting the user, and counting them double-counts whatever they quote.
    """
    try:
        lines = path.read_text(errors='replace').splitlines()
    except OSError:
        return
    for line in lines:
        if '"type"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        kind = row.get('type')
        if kind not in ('user', 'assistant'):
            continue
        content = (row.get('message') or {}).get('content')
        if isinstance(content, str):
            text, is_tool = content, False
        elif isinstance(content, list):
            is_tool = any(isinstance(b, dict) and b.get('type') in
                          ('tool_result', 'tool_use') for b in content)
            text = ' '.join(b.get('text', '') for b in content
                            if isinstance(b, dict) and b.get('type') == 'text')
        else:
            continue
        if kind == 'user':
            if is_tool and not text.strip():
                continue
            stripped = text.strip()
            if stripped.startswith(('<', 'Caveat:')) or \
               'This session is being continued from a previous' in stripped[:120]:
                continue
        yield kind, text


def tool_errors(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(errors='replace').splitlines()
                   if '"is_error":true' in line.replace(' ', ''))
    except OSError:
        return 0


def opening_words(text: str, n: int = 6) -> str:
    return ' '.join(re.findall(r'[a-z0-9]+', text.lower())[:n])


def analyze(path: Path) -> dict:
    user_texts, assistant_count = [], 0
    for role, text in turns(path):
        if role == 'assistant':
            assistant_count += 1
        elif text.strip():
            user_texts.append(text.strip())

    corrections = [t for t in user_texts
                   if len(t) <= MAX_CORRECTION_CHARS and
                   (CORRECTION.search(t) or FRICTION_WORDS.search(t))]

    openings = Counter(opening_words(t) for t in user_texts if len(t) > 25)
    repetition = sum(c - 1 for c in openings.values() if c > 1)

    first_ask = len(user_texts[0]) if user_texts else 0
    # Thrash, not size: many assistant turns against a short opening request.
    bloat = assistant_count >= 40 and first_ask < 300

    errors = tool_errors(path)
    # Rate, not count. The first version summed raw counts and ranked the four
    # longest sessions on the machine at the top: a 4,000-turn session accumulates
    # more of everything, including more of whatever went fine. Corrections per user
    # turn asks how often the user had to push back, which is the thing.
    #
    # Tool errors are dropped from the score entirely. They scale with length and a
    # failed grep is not a failed session; kept in the record as context only.
    rate = len(corrections) / len(user_texts) if user_texts else 0.0
    score = round(100 * rate + (5 if bloat else 0), 1)
    return {
        'session': path.stem[:8],
        'user_turns': len(user_texts),
        'assistant_turns': assistant_count,
        'corrections': len(corrections),
        'repetition': repetition,
        'tool_errors': errors,
        'bloat': bloat,
        'friction_score': score,
        'correction_rate': round(rate, 3),
        'sample_correction': corrections[0][:110] if corrections else '',
        'first_ask': (user_texts[0][:110] if user_texts else ''),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--logs', type=Path,
                   default=Path.home() / '.claude' / 'projects')
    p.add_argument('--out', type=Path)
    p.add_argument('--top', type=int, default=8)
    a = p.parse_args()

    rows = [analyze(f) for f in sorted(a.logs.rglob('*.jsonl'))
            if not f.stem.startswith('agent-')]
    # A short session cannot produce a meaningful rate: one correction in two turns
    # is 50% and means nothing. Ten real user turns is the floor.
    rows = [r for r in rows if r['user_turns'] >= 10]
    rows.sort(key=lambda r: -r['friction_score'])

    print(f'{len(rows)} real sessions with at least 10 user turns '
      f'(subagent transcripts excluded)\n')
    print('=== HIGHEST FRICTION ===')
    for r in rows[:a.top]:
        print(f"[{r['session']}] score={r['friction_score']:<6} "
              f"corr={r['corrections']}/{r['user_turns']} err={r['tool_errors']} "
              f"turns={r['assistant_turns']}")
        print(f"    asked: {r['first_ask']}")
        if r['sample_correction']:
            print(f"    said:  {r['sample_correction']}")
    print('\n=== LOWEST FRICTION ===')
    for r in rows[-a.top:]:
        print(f"[{r['session']}] score={r['friction_score']:<6} "
              f"corr={r['corrections']}/{r['user_turns']} err={r['tool_errors']} "
              f"turns={r['assistant_turns']}")
        print(f"    asked: {r['first_ask']}")

    if a.out:
        a.out.write_text(json.dumps(rows, indent=1))
        print(f'\nwrote {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
