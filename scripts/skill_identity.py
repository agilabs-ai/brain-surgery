#!/usr/bin/env python3
"""Compute a stable local bundle fingerprint and read registry identity claims.
No network requests. Registry verification is intentionally external.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re
from pathlib import Path

EXCLUDE_DIRS={'.git','__pycache__','.venv','venv','node_modules'}
EXCLUDE_FILES={'.DS_Store'}


def metadata_from_skill(path: Path) -> dict[str,str]:
    text=path.read_text(encoding='utf-8',errors='replace')
    if not text.startswith('---'): return {}
    header=text.split('---',2)[1]
    out={}
    for key in ('name','edge-id','edge-version','edge-url'):
        # metadata keys may be nested under `metadata:`; indentation is intentionally ignored.
        m=re.search(r'^\s*'+re.escape(key)+r':\s*([^\n]+)',header,re.M)
        if m: out[key]=m.group(1).strip().strip('"\'')[:500]
    return out


def bundle_fingerprint(root: Path) -> tuple[str,list[str]]:
    if not root.is_dir() or root.is_symlink(): raise ValueError('skill directory unavailable')
    h=hashlib.sha256(); files=[]
    for parent,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDE_DIRS and not (Path(parent)/d).is_symlink())
        for name in sorted(names):
            p=Path(parent)/name
            if name in EXCLUDE_FILES or p.is_symlink() or name.endswith(('.swp','~')): continue
            rel=p.relative_to(root).as_posix(); data=p.read_bytes()
            h.update(rel.encode('utf-8'));h.update(b'\0');h.update(len(data).to_bytes(8,'big'));h.update(data);h.update(b'\0')
            files.append(rel)
    return h.hexdigest(),files


def inspect(root: Path) -> dict:
    skill_md=root/'SKILL.md'
    if not skill_md.is_file(): raise ValueError('SKILL.md missing')
    meta=metadata_from_skill(skill_md); digest,files=bundle_fingerprint(root)
    claimed=meta.get('edge-id')
    return {
        'name':meta.get('name',root.name),
        'edge_id_claim':claimed,
        'edge_version_claim':meta.get('edge-version'),
        'edge_url_claim':meta.get('edge-url'),
        'bundle_sha256':digest,
        'files_hashed':files,
        'identity_state':'claimed_public_unverified' if claimed else 'local_private',
        'note':'Registry verification is required before labeling a skill verified_public or modified_public.'
    }


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--skill-dir',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args()
    try: result=inspect(a.skill_dir.resolve())
    except (OSError,ValueError) as e:p.exit(2,f'Identity check failed: {e}\n')
    text=json.dumps(result,indent=2)
    if a.out:a.out.write_text(text+'\n')
    else:print(text)
if __name__=='__main__':main()
