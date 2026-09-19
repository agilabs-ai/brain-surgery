#!/usr/bin/env python3
"""Score a rendered report against a frozen rubric, using a panel of judges.

The point is to stop "is this report any good" being settled by whoever is in
the room. Each judge gets one discipline, one rubric, and the same artifact,
and has to return a number per criterion plus a concrete, quotable defect for
anything it marks down. A judge that scores low without naming the offending
element is not returning a finding, it is returning a mood.

The rubric is frozen in this file on purpose. Editing the rubric between runs
means the scores across runs are not comparable, which is the same mistake as
moving the verifier between arms of the task grid.

Judges run headless on the subscription, one process each, in parallel.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_grid import resolve_claude_bin  # noqa: E402

SCALE = """Score each criterion 0-10, where:
  0-3  broken: a reader is actively misled, or cannot find the answer at all
  4-6  serviceable: correct but forgettable, or correct but takes effort to read
  7-8  good: a competent professional would ship this
  9-10 excellent: this is the version other people copy

Anchor every score below 7 to a specific element you can quote from the
artifact. "The subhead is vague" is not a finding. "The subhead reads 'Your
setup was worth more than a model upgrade', which states a comparison without
giving either quantity" is a finding."""

PANEL = {
    'chart-integrity': {
        'role': 'You are a data visualisation reviewer in the Tufte and Cleveland tradition. '
                'You care about whether the encoding is honest and whether the reader can do '
                'the comparison the chart claims to support.',
        'criteria': [
            'Truthfulness of encoding: does the visual length or position match the number, with no truncated or dishonest baseline',
            'Does every chart answer a question the reader actually has, rather than decorating a number already in the text',
            'Is uncertainty shown where uncertainty exists (intervals, denominators, sample size) rather than hidden behind a clean bar',
            'Data-ink: is there a chart here that is really a table, or a table that should be a chart',
            'Labelling: can the chart be read without hunting for a legend or a footnote',
        ],
    },
    'so-what': {
        'role': 'You are a senior partner at a top-tier strategy consultancy reviewing a client '
                'deliverable. You judge by the pyramid principle: the answer comes first, the '
                'support hangs beneath it, and every page earns its place.',
        'criteria': [
            'Is there a single governing answer stated in the first screen, in the client\'s language, not the builder\'s',
            'Does the headline state a result rather than argue a thesis',
            'Could a busy reader stop after the first screen and still have the decision-relevant answer',
            'Is every subsequent section support for that answer, or is some of it the author showing work',
            'Is the recommended action unambiguous, including what happens if the reader does nothing',
        ],
    },
    'statistical-honesty': {
        'role': 'You are a statistician reviewing a performance claim before it is published. '
                'You have seen every way a small sample gets dressed up as a result, and you '
                'assume the author is fooling themselves rather than lying.',
        'criteria': [
            'Is the denominator visible everywhere a rate or a delta appears',
            'Does the strength of the language match the strength of the evidence at this sample size',
            'Are units meaningful: is a "point" a real unit here, or is it one task wearing a lab coat',
            'Are the controls and confounds stated where a reader would otherwise assume more rigour than exists',
            'Would a sceptical reader with the underlying data accuse this page of over-claiming',
        ],
    },
    'prompt-replaceable': {
        'role': 'You are a sceptical technical buyer who has been pitched a lot of AI tools. Your '
                'default assumption is that any given output could have been produced by typing a '
                'paragraph into a chat window, and you need to be convinced otherwise. You are not '
                'hostile, you are just expensive to impress.',
        'criteria': [
            'Is there anything on this page that could NOT have been produced by prompting a model with a good prompt',
            'Does the page show evidence of work actually having been run: real measurements, real counts, things that had to be executed rather than asserted',
            'Could the reader reproduce this claim themselves, and does the page tell them how',
            'Is the specific machine, setup and task set visible, or is this generic enough to be about anyone',
            'After reading, do you believe a measurement happened, or do you suspect a template was filled in',
        ],
    },
    'cold-open': {
        'role': 'You are a competent engineer who was sent this link by a friend with no explanation. '
                'You have never heard of this product. You will give it about fifteen seconds before '
                'deciding whether to keep reading.',
        'criteria': [
            'Within ten seconds, do you know what this thing is and what it did',
            'Do you know whose setup this is about and what was actually measured',
            'Is there jargon that stops you, or a term used before it is defined',
            'Do you know what you are being asked to do next, if anything',
            'Would you send this to someone else, and what would you say it is',
        ],
    },
    'craft': {
        'role': 'You are a design director reviewing a page that will be shared publicly by its '
                'author. You are allergic to work that looks like it came out of a template, and '
                'you can name the specific tells.',
        'criteria': [
            'Hierarchy: does the eye land on the most important thing first, and is that the right thing',
            'Typography: real scale and considered weights, or default sizes with bold sprinkled on',
            'Restraint: is the boldness spent in one place, with everything around it quiet',
            'Does this look generated: generic accent gradients, uniform card grids, mono all-caps eyebrow labels, emoji as section markers, everything centred',
            'Would the author be proud to put their name on this in front of people whose opinion they care about',
        ],
    },
}

PROMPT = """{role}

You are reviewing an HTML artifact. Read it carefully before scoring. Treat the
rendered result as what the reader sees, not the source as a programmer sees it.

{context}

RUBRIC

{scale}

Score these criteria:
{criteria}

Return ONLY a JSON object, no prose around it, in exactly this shape:

{{
  "scores": [{{"criterion": "<the criterion text, abbreviated>", "score": <0-10>, "finding": "<specific, quotable defect, or empty string if 7+>"}}],
  "overall": <0-10>,
  "single_worst_problem": "<the one thing to fix first, named concretely>",
  "single_best_thing": "<what is already working and must not be lost in a rewrite>",
  "verdict": "<one sentence: would you ship this>"
}}

The artifact follows.

--- BEGIN ARTIFACT ---
{artifact}
--- END ARTIFACT ---
"""


#: Same hazard as the task grid: a host can put a wrapper ahead of the real CLI
#: on PATH, and AX41's adds `--chrome` to every invocation. Six judges running
#: in parallel would open six browsers on a box that is already tight on memory.
CLAUDE_BIN = 'claude'


def run_judge(name, spec, artifact, context, model, timeout):
    criteria = '\n'.join(f'{i+1}. {c}' for i, c in enumerate(spec['criteria']))
    prompt = PROMPT.format(role=spec['role'], scale=SCALE, criteria=criteria,
                           artifact=artifact, context=context)
    started = time.time()
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, '--print', '--model', model, '--setting-sources', '',
             '--strict-mcp-config', '--permission-mode', 'bypassPermissions'],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return name, {'error': 'judge timed out'}
    out = proc.stdout.strip()
    # Judges wrap JSON in prose more often than they admit to, so pull the
    # outermost object rather than trusting the whole stdout to parse.
    m = re.search(r'\{.*\}', out, re.S)
    if not m:
        return name, {'error': 'no JSON in judge output', 'raw': out[:1500]}
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return name, {'error': f'bad JSON: {e}', 'raw': out[:1500]}
    parsed['seconds'] = round(time.time() - started, 1)
    parsed['model'] = model
    return name, parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--artifact', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--model', default='claude-fable-5-1')
    ap.add_argument('--context', default='', help='what the reader is meant to get from this page')
    ap.add_argument('--panel', default=','.join(PANEL))
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--claude-bin', default=None,
                    help='path to the real CLI, bypassing any PATH wrapper')
    a = ap.parse_args()

    global CLAUDE_BIN
    CLAUDE_BIN = resolve_claude_bin(a.claude_bin)

    artifact = a.artifact.read_text()
    if len(artifact) > 400_000:
        raise SystemExit('artifact too large to judge whole; split it first')
    names = [n.strip() for n in a.panel.split(',') if n.strip() in PANEL]

    results = {}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = [pool.submit(run_judge, n, PANEL[n], artifact, a.context, a.model, a.timeout)
                   for n in names]
        for fut in as_completed(futures):
            name, res = fut.result()
            results[name] = res
            print(f'  {name:22s} overall={res.get("overall", "ERR")}', flush=True)

    scored = [r['overall'] for r in results.values() if isinstance(r.get('overall'), (int, float))]
    report = {
        'artifact': str(a.artifact),
        'model': a.model,
        'judged_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'panel_mean': round(sum(scored) / len(scored), 2) if scored else None,
        'judges': results,
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2))
    print(f'\npanel mean: {report["panel_mean"]}')
    for name, r in sorted(results.items()):
        if r.get('single_worst_problem'):
            print(f'  {name}: {r["single_worst_problem"]}')


if __name__ == '__main__':
    main()
