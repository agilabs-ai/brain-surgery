"""Shared local-only file utilities. Python 3.10+, standard library only."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 8 * 1024 * 1024

def load_json(path: Path, limit: int = MAX_JSON_BYTES) -> Any:
    if path.is_symlink():
        raise ValueError(f'Refusing a symlink: {path}')
    with path.open('rb') as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'File exceeds {limit} byte limit: {path}')
    return json.loads(data)

def write_json(path: Path, data: Any) -> None:
    """Atomic owner-only output. No network; no edits to input files."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError('Refusing to replace a symlink')
    fd, name = tempfile.mkstemp(prefix='.brain-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def digest(data: Any) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()

def file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Not a regular file: {path}')
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def safe_relative(value: str) -> Path:
    p = Path(value)
    if not value or p.is_absolute() or any(x in {'..', ''} for x in p.parts):
        raise ValueError('Expected a safe relative path')
    return p

def assert_inside(path: Path, root: Path) -> Path:
    result = path.resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError('Path escaped the declared root')
    # Existing symlink components can escape after a later filesystem change.
    for part in [path] + list(path.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError('Symlink components are not supported')
    return result
