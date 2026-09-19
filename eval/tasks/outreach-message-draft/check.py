#!/usr/bin/env python3
# provenance: shape `outbound-message-draft`, seen in 9 sessions (conservative count).
# Hard rules enforced: HR-1 (no em dashes, any encoding), HR-5 (German to a human uses
# real umlauts, never the ASCII transliteration kept in repo files), HR-12 (no compliance
# boilerplate in outreach), plus the per-channel length ceiling from the shape entry.
"""Verifier for outreach-message-draft."""
import re
import sys
from pathlib import Path

DASH = re.compile(r'[—–]|&mdash;|&ndash;|&#8212;|&#8211;|&#x2014;|&#x2013;', re.I)
URL = re.compile(r'https?://[^\s<>()\[\]"\',]+')
COMPLIANCE = ['dsgvo', 'gdpr', 'ai act', 'datenschutz', 'privacy notice',
              'privacy policy', 'art. 6', 'widerspruch', 'widersprechen']
# ASCII transliterations that belong in repo files, never in a message to a person
TRANSLIT = ['fuer', 'ueber', 'koennen', 'koennt', 'waere', 'muesste', 'muessen',
            'haenge', 'frueh', 'moechte', 'gruesse', 'gruss', 'zurueck', 'naechste',
            'naechsten', 'natuerlich', 'spaeter', 'wuerde', 'wuerden', 'hoeren',
            'gespraech', 'rueckmeldung', 'ueberlegen', 'schoen', 'groesse']


def fail(msg):
    print(msg)
    sys.exit(1)


ws = Path(sys.argv[1])
draft = None
for name in ('draft.md', 'draft.txt', 'DRAFT.md', 'draft.markdown'):
    if (ws / name).exists():
        draft = ws / name
        break
if draft is None:
    fail('draft.md missing')
text = draft.read_text(encoding='utf-8', errors='replace').strip()
if not text:
    fail(f'{draft.name} is empty')

m = DASH.search(text)
if m:
    s = max(0, m.start() - 35)
    fail(f'em dash in draft: ...{text[s:m.end() + 35]!r}')

low = text.lower()
for term in COMPLIANCE:
    if term in low:
        i = low.index(term)
        fail(f'compliance boilerplate {term!r} in the draft: '
             f'...{text[max(0, i - 40):i + 60]!r}')

for u in URL.findall(text):
    if '/legal/' in u or 'privacy' in u.lower() or 'datenschutz' in u.lower():
        fail(f'draft links a policy page: {u!r}')

words = len(text.split())
if words > 60:
    fail(f'draft is {words} words; a WhatsApp reply gets 60 at most')

if not re.search(r'[äöüÄÖÜß]', text):
    fail('draft has no umlauts; German written to a person uses ä ö ü ß, not ae/oe/ue')
for t in TRANSLIT:
    if re.search(r'\b' + t + r'\w*\b', low):
        hit = re.search(r'\b' + t + r'\w*\b', low).group(0)
        fail(f'ASCII transliteration {hit!r} in a message to a person; use real umlauts')

# the reply has to actually answer her two questions: the effort, and the deadline
if 'freitag' not in low:
    fail('draft never answers when we need to hear back (Freitag)')
if not any(k in low for k in ('stunde', 'logo', 'zitat')):
    fail('draft never answers how much work it is on their side (Logo / Zitat / Stunde)')

print('ok')
sys.exit(0)
