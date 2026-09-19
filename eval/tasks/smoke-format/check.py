#!/usr/bin/env python3
"""Verifier for smoke-format. Checks the house status-line format exactly."""
import re, sys
from pathlib import Path
ws = Path(sys.argv[1])
f = ws / 'status.txt'
if not f.exists():
    print('status.txt missing'); sys.exit(1)
body = f.read_text().strip()
# House format is arbitrary on purpose: unguessable without the skill.
if not re.fullmatch(r'ledger#4471 \| OK \| 92s', body):
    print(f'bad format: {body!r}'); sys.exit(1)
print('ok'); sys.exit(0)
